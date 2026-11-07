import hashlib
import io
import json
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

import httpx

from bootstrap import installed_root
from kareem_ai.core import ProviderError
from kareem_ai.updates import (REPOSITORY, Release, activate, download_release, install_bundle,
                              latest_release, version_tuple)
from kareem_ai.voice import speech_text, transcribe, wav_audio


def bundle(version="0.3.0", extra=None):
    files = {"bundle.json": json.dumps({"schema": 1, "version": version}),
             "kareem_ai/__init__.py": "", "kareem_ai/app.py": "# fixture, never executed",
             "kareem_ai/core.py": "", "bootstrap.py": "", "requirements.txt": ""}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, value in files.items():
            z.writestr("kareem-ai/" + name, value)
        for name, value in (extra or {}).items():
            z.writestr(name, value)
    return out.getvalue()


def release_for(payload, version="0.3.0"):
    return Release(version, "notes", f"https://github.com/{REPOSITORY}/releases/download/v{version}/Kareem-AI-v{version}.zip",
                   hashlib.sha256(payload).hexdigest(), len(payload))


class VoiceTests(unittest.IsolatedAsyncioTestCase):
    def test_audio_is_valid_wav(self):
        audio = wav_audio(b"\x00\x00" * 1600, 16000, 1)
        with wave.open(io.BytesIO(audio)) as f:
            self.assertEqual(f.getframerate(), 16000)
            self.assertEqual(f.getnchannels(), 1)
            self.assertEqual(f.getnframes(), 1600)

    def test_invalid_audio_rejected(self):
        with self.assertRaises(ValueError):
            wav_audio(b"", 16000, 1)

    def test_spoken_text_excludes_code_and_actions(self):
        self.assertEqual(speech_text("## Hello **Kareem**\n```action\n{\"type\":\"run_python\"}\n```\n[Help](https://example.com)"),
                         "Hello Kareem\n\nHelp")

    async def test_transcription_multipart_and_no_chat_send(self):
        requests = []
        def handler(request):
            requests.append(request)
            self.assertEqual(request.url.path, "/openai/v1/audio/transcriptions")
            self.assertIn(b"whisper-large-v3-turbo", request.content)
            self.assertIn(b"recording.wav", request.content)
            self.assertEqual(request.headers["authorization"], "Bearer fake-key")
            return httpx.Response(200, json={"text": " hello Kareem "})
        text = await transcribe(wav_audio(b"\x00\x00" * 100, 16000, 1), "fake-key", transport=httpx.MockTransport(handler))
        self.assertEqual(text, "hello Kareem")
        self.assertEqual(len(requests), 1)

    async def test_transcription_limits_not_retried(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(429, text="sensitive provider content")
        with self.assertRaises(ProviderError) as error:
            await transcribe(b"recording", "fake-key", transport=httpx.MockTransport(handler))
        self.assertNotIn("sensitive", str(error.exception))
        self.assertEqual(len(requests), 1)


class UpdateTests(unittest.IsolatedAsyncioTestCase):
    def test_numeric_versions(self):
        self.assertGreater(version_tuple("0.10.0"), version_tuple("0.2.0"))
        for value in ("../1", "1.0", "1.0.0-beta", "01.0.0"):
            with self.assertRaises(ValueError):
                version_tuple(value)

    async def test_latest_release_validation(self):
        payload = bundle()
        release = release_for(payload)
        data = {"tag_name": "v0.3.0", "body": "notes", "assets": [{"name": "Kareem-AI-v0.3.0.zip",
                "browser_download_url": release.url, "digest": "sha256:" + release.digest, "size": release.size}]}
        self.assertEqual(await latest_release(httpx.MockTransport(lambda _: httpx.Response(200, json=data))), release)
        data["assets"][0]["browser_download_url"] = "https://evil.example/a.zip"
        with self.assertRaises(ValueError):
            await latest_release(httpx.MockTransport(lambda _: httpx.Response(200, json=data)))

    async def test_missing_release(self):
        with self.assertRaisesRegex(ValueError, "No published release"):
            await latest_release(httpx.MockTransport(lambda _: httpx.Response(404)))

    async def test_download_checksum_and_redirect_limits(self):
        payload = bundle()
        release = release_for(payload)
        self.assertEqual(await download_release(release, httpx.MockTransport(lambda _: httpx.Response(200, content=payload))), payload)
        with self.assertRaisesRegex(ValueError, "match|size"):
            await download_release(release, httpx.MockTransport(lambda _: httpx.Response(200, content=b"corrupt")))
        with self.assertRaisesRegex(ValueError, "trusted GitHub"):
            await download_release(release, httpx.MockTransport(lambda _: httpx.Response(302, headers={"location": "https://evil.example/a.zip"})))

    def test_install_separate_then_activate_preserves_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "chats").mkdir()
            (root / "chats" / "chat.json").write_text("history")
            (root / "settings.json").write_text("settings")
            payload = bundle()
            target = install_bundle(payload, release_for(payload), root)
            self.assertFalse((root / "current.json").exists())
            self.assertEqual(target, root / "releases" / "0.3.0")
            activate(target, root)
            self.assertEqual(installed_root(Path("source"), root), target)
            self.assertEqual((root / "chats" / "chat.json").read_text(), "history")
            self.assertEqual((root / "settings.json").read_text(), "settings")

    def test_reject_bad_archives_before_extraction(self):
        for name in ("kareem-ai/../outside.txt", "kareem-ai/C:/secret", "kareem-ai/user-data/key",
                     "kareem-ai/CON.txt", "kareem-ai/back\\slash", "kareem-ai/bundle.JSON"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                payload = bundle(extra={name: "bad"})
                if "\\" in name:
                    # ZipInfo normalizes Windows separators when creating fixtures. Mutate
                    # both directory records to represent an actually malformed archive.
                    payload = payload.replace(name.replace("\\", "/").encode(), name.encode())
                root = Path(folder)
                with self.assertRaises(ValueError):
                    install_bundle(payload, release_for(payload), root)
                self.assertEqual(list((root / "releases").iterdir()), [])
                self.assertFalse((root / "current.json").exists())

    def test_wrong_manifest_and_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            payload = bundle(version="0.4.0")
            with self.assertRaisesRegex(ValueError, "version"):
                install_bundle(payload, release_for(payload), root)
            with self.assertRaisesRegex(ValueError, "verification"):
                install_bundle(b"tampered", release_for(payload), root)

    def test_bootstrap_rejects_unsafe_pointer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "current.json").write_text('{"version":"../../outside"}')
            self.assertEqual(installed_root(Path("source"), root), Path("source"))


if __name__ == "__main__":
    unittest.main()
