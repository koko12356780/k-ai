import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

import httpx
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from kareem_ai.app import Settings, STYLE, Window
from kareem_ai.core import Engine
from kareem_ai.storage import Store
from kareem_ai.voice_ui import VoiceDialog
from kareem_ai.app import Worker
from kareem_ai.updates import Release
from kareem_ai.themes import NAMES


class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.key_patch = patch("kareem_ai.app.get_key", return_value="")
        self.key_patch.start()
        self.window = Window(Store(Path(self.temp.name)))
        self.window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.window.show()
        QTest.qWait(100)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.key_patch.stop()
        self.temp.cleanup()

    def test_welcome_and_settings(self):
        self.assertEqual(self.window.mode.currentText(), "Merge")
        self.assertFalse(self.window.stop_button.isEnabled())
        self.assertEqual(self.window.keys, {"Gemini": "", "Groq": ""})
        dialog = Settings(self.window)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.assertTrue(dialog.remember.isChecked())
        dialog.show()
        QTest.qWait(50)
        dialog.reject()
        output = os.environ.get("KAREEM_AI_SCREENSHOTS")
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
            self.window.grab().save(str(Path(output) / "welcome.png"))

    def test_chat_flow_merge_and_persistence(self):
        self.window.keys = {"Gemini": "fake-key", "Groq": "fake-key"}
        self.window.config = {"Gemini": "simulated-gemini", "Groq": "simulated-groq"}
        calls = []
        def handler(request):
            calls.append(json.loads(request.content))
            text = "Independent test draft" if len(calls) < 3 else (
                "## Your two-model workspace is ready\n\nThis is a **simulated test reply**, not a live API response.\n\n"
                "Gemini and Groq drafted independently, then the merge pass combined their answers.\n\n"
                "You can switch models, review their contributions, and approve proposed file changes.")
            return httpx.Response(200, text="data: " + json.dumps({"choices": [{"delta": {"content": text}}]}) + "\n\ndata: [DONE]\n\n")
        transport = httpx.MockTransport(handler)
        with patch("kareem_ai.app.Engine", side_effect=lambda providers: Engine(providers, transport)), \
             patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window.composer.setPlainText("Show me how the two AIs work together. (UI test)")
            self.window.send()
            deadline = time.monotonic() + 10
            while self.window.busy() and time.monotonic() < deadline:
                QTest.qWait(20)
            QTest.qWait(100)
        self.assertFalse(self.window.busy())
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(self.window.chat["messages"]), 2)
        self.assertEqual(len(self.window.chat["runs"][0]["drafts"]), 2)
        self.assertTrue(self.window.send_button.isEnabled())
        saved = self.window.store.chats()[0]
        self.assertEqual(saved["messages"][1]["content"], self.window.chat["messages"][1]["content"])
        for file in Path(self.temp.name).rglob("*"):
            if file.is_file():
                self.assertNotIn("fake-key", file.read_text(encoding="utf-8"))
        output = os.environ.get("KAREEM_AI_SCREENSHOTS")
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
            self.window.grab().save(str(Path(output) / "merge-test.png"))

    def test_denied_action_has_no_effect(self):
        self.window.project_root = self.temp.name
        with patch("kareem_ai.app.execute") as execute, patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.window.review_action({"type": "write_file", "path": "denied.txt", "content": "no"})
            execute.assert_not_called()
        self.assertFalse((Path(self.temp.name) / "denied.txt").exists())

    def test_theme_preview_cancel_and_save(self):
        dialog = Settings(self.window)
        for name in NAMES:
            dialog.theme.setCurrentText(name)
            self.assertIn("QWidget", self.app.styleSheet())
        dialog.reject()
        self.assertIn("#10131c", self.app.styleSheet())
        dialog = Settings(self.window)
        dialog.theme.setCurrentText("Daylight")
        output = os.environ.get("KAREEM_AI_SCREENSHOTS")
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            dialog.show()
            dialog.tabs.setCurrentIndex(1)
            QTest.qWait(50)
            dialog.grab().save(str(Path(output) / "themes.png"))
            dialog.tabs.setCurrentIndex(3)
            QTest.qWait(50)
            dialog.grab().save(str(Path(output) / "updates.png"))
        dialog.remember.setChecked(False)
        dialog.read_replies.setChecked(True)
        with patch("kareem_ai.app.set_key"):
            self.assertTrue(dialog.save_for_restart())
        self.assertEqual(self.window.store.config()["theme"], "Daylight")
        self.assertTrue(self.window.store.config()["read_replies"])
        self.assertIn("#f5f6fb", self.app.styleSheet())
        dialog.accept()

    def test_voice_no_device_and_transcript_not_auto_sent(self):
        with patch("kareem_ai.voice_ui.QMediaDevices.audioInputs", return_value=[]):
            voice = VoiceDialog(self.window, Worker)
        self.assertFalse(voice.record.isEnabled())
        self.assertIn("No microphone", voice.status.text())
        output = os.environ.get("KAREEM_AI_SCREENSHOTS")
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
            voice.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            voice.show()
            QTest.qWait(50)
            voice.grab().save(str(Path(output) / "voice.png"))
        voice.transcript.setPlainText("hello from voice")
        with patch.object(self.window, "send") as send:
            voice.use_transcript()
            send.assert_not_called()
        self.assertEqual(self.window.composer.toPlainText(), "hello from voice")
        self.assertEqual(voice.audio, b"")

    def test_voice_recording_with_simulated_microphone(self):
        from unittest.mock import Mock
        device = Mock()
        device.description.return_value = "Simulated microphone"
        device.isFormatSupported.return_value = True
        source = Mock()
        source.start.side_effect = lambda buffer: buffer.write(b"\x00\x00" * 1600)
        with patch("kareem_ai.voice_ui.QMediaDevices.audioInputs", return_value=[device]), \
             patch("kareem_ai.voice_ui.QMediaDevices.defaultAudioInput", return_value=device), \
             patch("kareem_ai.voice_ui.QAudioSource", return_value=source), \
             patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            voice = VoiceDialog(self.window, Worker)
            voice.start_recording()
            self.assertTrue(voice.timer.isActive())
            voice.stop_recording()
            self.assertTrue(voice.audio.startswith(b"RIFF"))
            self.assertTrue(voice.upload.isEnabled())
            self.assertFalse(voice.timer.isActive())
            source.stop.assert_called_once()
            voice.reject()
            self.assertEqual(voice.audio, b"")

    def test_updates_require_newer_version_and_approval(self):
        dialog = Settings(self.window)
        updates = dialog.updates
        self.assertFalse(updates.install.isEnabled())
        updates.checked(Release("0.1.0", "older", "", "", 1))
        updates.finished()
        self.assertFalse(updates.install.isEnabled())
        updates.checked(Release("0.3.0", "new version notes", "", "", 1))
        updates.finished()
        self.assertTrue(updates.install.isEnabled())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No), \
             patch("kareem_ai.update_ui.download_release") as download:
            updates.install_update()
            download.assert_not_called()
        self.assertFalse(updates.running())
        dialog.reject()

    def test_voice_picker_preview_is_local_and_choice_saves(self):
        from unittest.mock import Mock
        from PySide6.QtCore import QLocale
        voice = Mock()
        voice.name.return_value = "Test voice"
        voice.locale.return_value = QLocale("en_US")
        with patch.object(self.window, "voice_options", return_value=[voice]), \
             patch.object(self.window, "say") as say, \
             patch("kareem_ai.voice_ui.QMediaDevices.audioInputs", return_value=[]):
            dialog = VoiceDialog(self.window, Worker)
            dialog.reply_voice.setCurrentIndex(dialog.reply_voice.findData("en_US|Test voice"))
            dialog.preview_voice.click()
            self.assertEqual(say.call_args.args[1], "en_US|Test voice")
            self.assertNotIn("speech_voice", self.window.store.config())
            dialog.save_voice()
            self.assertEqual(self.window.store.config()["speech_voice"], "en_US|Test voice")
            dialog.reject()

    def test_settings_auto_load_voices_and_preview_without_saving(self):
        from unittest.mock import Mock
        from PySide6.QtCore import QLocale
        voice = Mock()
        voice.name.return_value = "Test Arabic voice"
        voice.locale.return_value = QLocale("ar_SA")
        with patch.object(self.window, "voice_options", return_value=[voice]), \
             patch.object(self.window, "say") as say:
            dialog = Settings(self.window)
            dialog.tabs.setCurrentIndex(2)
            self.assertEqual(dialog.voice_choice.count(), 14)
            dialog.voice_choice.setCurrentIndex(dialog.voice_choice.findData("ar_SA|Test Arabic voice"))
            dialog.rate.setValue(20)
            dialog.pitch.setValue(-15)
            sample = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Try this voice")
            sample.click()
            self.assertEqual(say.call_args.args[1:], ("ar_SA|Test Arabic voice", .2, -.15))
            self.assertNotIn("speech_voice", self.window.store.config())
            dialog.reject()

    def test_cloud_voice_denied_never_uses_api_or_windows_speech(self):
        from kareem_ai.cloud_voice import DEFAULT_CLOUD_VOICE
        self.window.keys["Groq"] = "fake-key"
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No), \
             patch("kareem_ai.app.synthesize") as synthesize, \
             patch.object(self.window, "ensure_speaker") as windows:
            self.window.say("Hello", DEFAULT_CLOUD_VOICE)
            synthesize.assert_not_called()
            windows.assert_not_called()
        self.assertFalse(self.window.speech_active())

    def test_cloud_voice_generation_and_mute_cancellation(self):
        import asyncio
        from kareem_ai.cloud_voice import CloudAudio, DEFAULT_CLOUD_VOICE
        self.window.keys["Groq"] = "fake-key"
        async def generate(*args):
            await asyncio.sleep(.05)
            return CloudAudio(b"simulated audio", 1, 5, False)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
             patch("kareem_ai.app.synthesize", side_effect=generate) as synthesize, \
             patch.object(self.window, "cloud_audio_ready") as play:
            self.window.say("Hello", DEFAULT_CLOUD_VOICE)
            deadline = time.monotonic() + 5
            while self.window.speech_active() and time.monotonic() < deadline:
                QTest.qWait(20)
            QTest.qWait(50)
            self.assertEqual(synthesize.await_count, 1)
            play.assert_called_once()
            play.reset_mock()
            self.window.say("Hello again", DEFAULT_CLOUD_VOICE)
            self.window.stop_speaking()
            deadline = time.monotonic() + 5
            while self.window.speech_active() and time.monotonic() < deadline:
                QTest.qWait(20)
            QTest.qWait(50)
            play.assert_not_called()
        self.assertFalse(self.window.speech_active())

    def test_cloud_audio_uses_pcm_memory_buffer_without_media_codecs(self):
        from unittest.mock import Mock
        from kareem_ai.cloud_voice import CloudAudio
        from kareem_ai.voice import wav_audio
        player = Mock()
        audio = wav_audio(b"\x00\x00" * 100, 16000, 1)
        device = Mock()
        device.isNull.return_value = False
        device.isFormatSupported.return_value = True
        with patch("PySide6.QtMultimedia.QAudioSink", return_value=player), \
             patch("PySide6.QtMultimedia.QMediaDevices.defaultAudioOutput", return_value=device):
            self.window.cloud_audio_ready(CloudAudio(audio, 1, 5, False), self.window.speech_generation, .2)
            self.assertEqual(bytes(self.window.audio_buffer.data()), b"\x00\x00" * 100)
            player.start.assert_called_once_with(self.window.audio_buffer)
            self.window.stop_speaking()
            self.assertIsNone(self.window.audio_buffer)


if __name__ == "__main__":
    unittest.main()
