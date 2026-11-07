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
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

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


if __name__ == "__main__":
    unittest.main()
