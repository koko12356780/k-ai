import io
import json
import unittest
import wave

import httpx

from kareem_ai.cloud_voice import (ARABIC_MODEL, CLOUD_VOICES, DEFAULT_CLOUD_VOICE,
    cloud_voice, combine_wav, speech_chunks, synthesize, voice_setup_url)
from kareem_ai.core import ProviderError
from kareem_ai.voice import wav_audio


class CloudVoiceTests(unittest.IsolatedAsyncioTestCase):
    def test_twelve_voices_with_correct_language_model(self):
        self.assertEqual(len(CLOUD_VOICES), 12)
        self.assertEqual(len({value for _, value in CLOUD_VOICES}), 12)
        self.assertEqual(cloud_voice("groq|" + ARABIC_MODEL + "|noura"), (ARABIC_MODEL, "noura"))
        with self.assertRaises(ProviderError):
            cloud_voice("groq|unknown-model|voice")

    def test_chunk_boundaries_and_request_budget(self):
        for text in ("x" * 5000, "a normal sentence. " * 200, "مرحبا كريم " * 300):
            chunks, truncated = speech_chunks(text)
            self.assertTrue(truncated)
            self.assertLessEqual(len(chunks), 5)
            self.assertTrue(all(0 < len(chunk) <= 200 for chunk in chunks))
        chunks, truncated = speech_chunks("Hello Kareem!")
        self.assertEqual(chunks, ["Hello Kareem!"])
        self.assertFalse(truncated)

    async def test_speech_endpoint_and_combined_pcm(self):
        requests = []
        audio = wav_audio(b"\x00\x00" * 100, 16000, 1)
        def handle(request):
            requests.append(request)
            self.assertEqual(request.url.path, "/openai/v1/audio/speech")
            self.assertEqual(request.headers["authorization"], "Bearer fake-key")
            body = json.loads(request.content)
            self.assertEqual(body["voice"], "troy")
            self.assertEqual(body["response_format"], "wav")
            self.assertLessEqual(len(body["input"]), 200)
            return httpx.Response(200, content=audio, headers={"content-type": "audio/wav"})
        result = await synthesize("word " * 90, "fake-key", DEFAULT_CLOUD_VOICE,
                                  transport=httpx.MockTransport(handle))
        self.assertEqual(result.requests, len(requests))
        self.assertEqual(result.requests, 3)
        with wave.open(io.BytesIO(result.audio)) as wav:
            self.assertEqual(wav.getnframes(), 100 * 3)

    async def test_quota_failure_no_retry_or_fallback(self):
        requests = []
        def handle(request):
            requests.append(request)
            return httpx.Response(429, text="private-error-message")
        with self.assertRaises(ProviderError) as error:
            await synthesize("Hello", "fake-key", DEFAULT_CLOUD_VOICE, transport=httpx.MockTransport(handle))
        self.assertEqual(len(requests), 1)
        self.assertNotIn("private-error-message", str(error.exception))

    async def test_no_key_no_request(self):
        def handle(_):
            self.fail("No request is allowed without a key")
        with self.assertRaises(ProviderError):
            await synthesize("Hello", "", DEFAULT_CLOUD_VOICE, transport=httpx.MockTransport(handle))

    async def test_required_terms_are_identified_without_echoing_private_data(self):
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(400, json={"error": {"code": "model_terms_required",
                "message": "requires terms acceptance secret-key private-input"}})
        with self.assertRaises(ProviderError) as error:
            await synthesize("private-input", "secret-key", DEFAULT_CLOUD_VOICE,
                             transport=httpx.MockTransport(handle))
        message = str(error.exception)
        self.assertIn("Groq voice setup", message)
        self.assertIn("does not accept terms for you", message)
        self.assertNotIn("secret-key", message)
        self.assertNotIn("private-input", message)
        self.assertEqual(len(calls), 1)

    def test_voice_setup_links_match_selected_model(self):
        from urllib.parse import parse_qs, urlsplit
        for _, selection in CLOUD_VOICES:
            url = urlsplit(voice_setup_url(selection))
            self.assertEqual(url.scheme, "https")
            self.assertEqual(url.netloc, "console.groq.com")
            self.assertEqual(parse_qs(url.query)["model"], [cloud_voice(selection)[0]])

    def test_invalid_and_mismatched_audio_rejected(self):
        with self.assertRaises(ProviderError):
            combine_wav([b"not audio"])
        a = wav_audio(b"\x00\x00" * 100, 16000, 1)
        b = wav_audio(b"\x00\x00" * 100, 24000, 1)
        with self.assertRaises(ProviderError):
            combine_wav([a, b])


if __name__ == "__main__":
    unittest.main()
