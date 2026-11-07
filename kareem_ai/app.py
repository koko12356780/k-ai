from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QTextBrowser, QVBoxLayout, QWidget, QTabWidget,
)

from .core import Answer, Engine, Provider, ProviderError, cancellable, discover
from .storage import Store, get_key, new_chat, set_key
from .tools import execute, prepare, proposals
from .themes import NAMES, stylesheet
from .voice_ui import VoiceDialog
from .update_ui import UpdatePanel
from .cloud_voice import DEFAULT_CLOUD_VOICE, synthesize, pcm_audio, voice_setup_url
from .characters import CHARACTERS, character_for


STYLE = '''
QWidget { background: #10131c; color: #e9edf6; font-family: 'Segoe UI'; font-size: 14px; }
QMainWindow { background: #10131c; }
QFrame#sidebar { background: #151a26; }
QFrame#sidebar QLabel { background: transparent; }
QLabel#brand { font-size: 24px; font-weight: 700; color: #eeeaff; }
QLabel#headline { font-size: 22px; font-weight: 650; }
QLabel#muted { color: #9da9bf; font-size: 12px; }
QLabel#badge { color: #b9acff; font-size: 12px; }
QPushButton { background: #232b3e; border: 1px solid #34405a; border-radius: 9px; padding: 9px 14px; }
QPushButton:hover { background: #303c55; }
QPushButton:disabled { color: #68748b; background: #1b2231; }
QPushButton#primary { background: #8c73f8; color: #0b0b18; font-weight: 700; border: none; }
QPushButton#primary:hover { background: #a18aff; }
QPushButton#primary:disabled { background: #1b2231; color: #68748b; border: 1px solid #34405a; }
QTabWidget::pane { border: 1px solid #34405a; border-radius: 8px; }
QTabBar::tab { background: #1b2231; color: #9da9bf; padding: 10px 16px; border: 1px solid #34405a; }
QTabBar::tab:selected { background: #2b304b; color: #d8cdff; }
QLineEdit, QPlainTextEdit, QComboBox { background: #1b2231; border: 1px solid #34405a; border-radius: 8px; padding: 9px; selection-background-color: #6251a9; }
QComboBox QAbstractItemView { background: #1b2231; }
QListWidget { border: none; background: transparent; outline: none; }
QListWidget::item { padding: 11px 8px; border-radius: 8px; }
QListWidget::item:selected { background: #2b304b; color: #d8cdff; }
QScrollArea, QTextBrowser { border: none; background: transparent; }
QFrame#card { background: #1a2130; border: 1px solid #2a344a; border-radius: 12px; }
QFrame#card QLabel, QFrame#card QTextBrowser { background: transparent; }
QSplitter::handle { background: #252d40; width: 1px; }
QScrollBar:vertical { width: 8px; background: #141a25; }
QScrollBar::handle:vertical { background: #36415b; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
'''


def button(text, callback, primary=False):
    result = QPushButton(text)
    result.clicked.connect(callback)
    if primary:
        result.setObjectName("primary")
    return result


class SafeBrowser(QTextBrowser):
    def __init__(self):
        super().__init__()
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)

    def loadResource(self, resource_type, url):
        # Model Markdown cannot load remote images or local files.
        return None


class Worker(QThread):
    event = Signal(str)
    token = Signal(str)
    success = Signal(object)
    failure = Signal(str)

    def __init__(self, factory):
        super().__init__()
        self.factory = factory
        self.cancel = threading.Event()

    def run(self):
        try:
            value = asyncio.run(cancellable(self.factory(self), self.cancel))
            self.success.emit(value)
        except asyncio.CancelledError:
            self.failure.emit("Stopped. Requests already accepted by providers may still count toward quota.")
        except (ProviderError, ValueError) as exc:
            self.failure.emit(str(exc))
        except Exception:
            self.failure.emit("The operation failed. Check your connection, Settings, and installed dependencies.")


class Settings(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.owner = parent
        self.worker = None
        self.original_theme = parent.config.get("theme", "Night")
        self.setWindowTitle("Settings · Kareem AI")
        self.resize(740, 750)
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        models_page = QWidget()
        self.tabs.addTab(models_page, "Models & keys")
        layout = QVBoxLayout(models_page)
        title = QLabel("Two minds. One conversation.")
        title.setObjectName("headline")
        layout.addWidget(title)
        note = QLabel("Use your own free-tier accounts. The app cannot verify billing status.\n"
                      "Do not enable paid billing if you want to stay free. No automatic retries or upgrades.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.keys, self.models = {}, {}
        self.refresh_buttons = []
        for name in ("Gemini", "Groq"):
            layout.addWidget(QLabel(name + " API key"))
            key = QLineEdit(parent.keys.get(name, ""))
            key.setEchoMode(QLineEdit.EchoMode.Password)
            key.setPlaceholderText("Paste here inside the app — never in chat")
            self.keys[name] = key
            layout.addWidget(key)
            row = QHBoxLayout()
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItem(parent.config.get(name, ""))
            combo.lineEdit().setPlaceholderText("Refresh, then select a chat model available on your free tier")
            self.models[name] = combo
            row.addWidget(combo, 1)
            refresh = button("Load models", lambda checked=False, n=name: self.refresh(n))
            self.refresh_buttons.append(refresh)
            row.addWidget(refresh)
            layout.addLayout(row)
            url = "https://aistudio.google.com/apikey" if name == "Gemini" else "https://console.groq.com/keys"
            link = button("Get a " + name + " key ↗", lambda checked=False, u=url: parent.approve_link(u))
            layout.addWidget(link)
        self.remember = QCheckBox("Remember keys securely in Windows Credential Manager")
        self.remember.setChecked(True)
        layout.addWidget(self.remember)
        self.status = QLabel("Model availability does not guarantee free access. Check your account's limits.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch()
        appearance = QWidget()
        self.tabs.addTab(appearance, "Appearance")
        theme_layout = QVBoxLayout(appearance)
        theme_title = QLabel("Make it yours.")
        theme_title.setObjectName("headline")
        theme_layout.addWidget(theme_title)
        theme_layout.addWidget(QLabel("Theme · preview changes immediately; Save keeps your choice."))
        self.theme = QComboBox()
        self.theme.addItems(NAMES)
        self.theme.setCurrentText(self.original_theme)
        self.theme.currentTextChanged.connect(parent.apply_theme)
        theme_layout.addWidget(self.theme)
        theme_layout.addWidget(QLabel("Night · classic purple\nDaylight · bright and clear\nOcean · deep blue\nMint · calm green\nRose · warm pink"))
        theme_layout.addStretch()
        voice_page = QWidget()
        self.tabs.addTab(voice_page, "Voice")
        voice_layout = QVBoxLayout(voice_page)
        voice_title = QLabel("Talk it through.")
        voice_title.setObjectName("headline")
        voice_layout.addWidget(voice_title)
        voice_note = QLabel("Cloud voices use Groq Orpheus: 6 English and 6 Arabic Saudi voices.\n"
                            "Each voice is its own character, shaping the AI's chat style and spoken replies.\n"
                            "Long readouts are limited to roughly 1,000 characters / 5 requests to protect quota.")
        voice_note.setWordWrap(True)
        voice_layout.addWidget(voice_note)
        self.read_replies = QCheckBox("Read completed replies aloud automatically")
        self.read_replies.setChecked(bool(parent.config.get("read_replies", False)))
        voice_layout.addWidget(self.read_replies)
        voice_layout.addWidget(QLabel("Transcription model (uses your Groq audio quota)"))
        self.stt_model = QComboBox()
        self.stt_model.addItems(["whisper-large-v3-turbo", "whisper-large-v3"])
        self.stt_model.setCurrentText(parent.config.get("stt_model", "whisper-large-v3-turbo"))
        voice_layout.addWidget(self.stt_model)
        voice_layout.addWidget(QLabel("Choose your character"))
        self.voice_choice = QComboBox()
        for character in CHARACTERS:
            self.voice_choice.addItem(character.name + " · " + character.title, character.selection)
        self.voice_choice.setCurrentIndex(self.voice_choice.findData(
            character_for(parent.config.get("speech_voice")).selection))
        voice_layout.addWidget(self.voice_choice)
        self.character_details = QLabel()
        self.character_details.setWordWrap(True)
        voice_layout.addWidget(self.character_details)
        self.voice_count = QLabel("12 cloud characters. Speech uses your Groq key and quota.")
        self.voice_count.setWordWrap(True)
        voice_layout.addWidget(self.voice_count)
        self.setup_voice = button("Groq voice setup ↗", self.open_voice_setup)
        voice_layout.addWidget(self.setup_voice)
        voice_layout.addWidget(button("Try this voice", lambda: parent.say(
            character_for(self.voice_choice.currentData()).preview,
            self.voice_choice.currentData())))
        voice_layout.addWidget(button("Stop speaking", parent.stop_speaking))
        more = QLabel("Choose a Groq voice above for cloud speech. Select an English or Arabic voice to match your text.\n"
                      "Groq quota, model access, and account billing apply; the app does not enable paid billing.")
        more.setWordWrap(True)
        voice_layout.addWidget(more)
        voice_layout.addStretch()
        self.updates = UpdatePanel(parent, Worker)
        self.tabs.addTab(self.updates, "Updates")
        self.voice_choice.currentIndexChanged.connect(lambda _: self.update_voice_controls())
        self.update_voice_controls()
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

    def update_voice_controls(self):
        character = character_for(self.voice_choice.currentData())
        self.character_details.setText(character.name + " · " + character.title + "\n" + character.summary)

    def open_voice_setup(self):
        selection = self.voice_choice.currentData()
        self.owner.approve_link(voice_setup_url(character_for(selection).selection))

    def refresh(self, name):
        if not self.keys[name].text().strip():
            self.status.setText("Paste your " + name + " key first.")
            return
        self.status.setText("Loading " + name + " models…")
        for b in self.refresh_buttons:
            b.setEnabled(False)
        self.buttons.setEnabled(False)
        p = Provider(name, self.keys[name].text().strip())
        self.worker = Worker(lambda _: discover(p))
        self.worker.success.connect(lambda models: self.loaded(name, models))
        self.worker.failure.connect(self.status.setText)
        self.worker.finished.connect(self.refresh_finished)
        self.worker.start()

    def loaded(self, name, models):
        previous = self.models[name].currentText()
        self.models[name].clear()
        self.models[name].addItem("")
        self.models[name].addItems(models)
        self.models[name].setCurrentText(previous)
        self.status.setText(f"Loaded {len(models)} {name} models. Choose a text/chat model with free quota in your account.")

    def refresh_finished(self):
        for b in self.refresh_buttons:
            b.setEnabled(True)
        self.buttons.setEnabled(True)

    def save(self):
        if self.save_for_restart():
            self.accept()

    def save_for_restart(self):
        if (self.worker and self.worker.isRunning()) or self.updates.running():
            self.status.setText("Wait for the current operation to finish before saving Settings.")
            return False
        values = {n: self.keys[n].text().strip() for n in self.keys}
        if self.remember.isChecked():
            try:
                for name, value in values.items():
                    set_key(name, value)
            except Exception:
                self.status.setText("Windows couldn't store a key. Uncheck Remember to use keys only for this session.")
                self.tabs.setCurrentIndex(0)
                return False
        else:
            try:
                for name in values:
                    set_key(name, "")
            except Exception:
                self.status.setText("Couldn't remove saved keys. Check Windows Credential Manager before continuing.")
                self.tabs.setCurrentIndex(0)
                return False
        self.owner.keys = values
        self.owner.config = {**self.owner.config, **{name: self.models[name].currentText().strip() for name in values},
            "theme": self.theme.currentText(), "read_replies": self.read_replies.isChecked(),
            "speech_voice": character_for(self.voice_choice.currentData()).selection,
            "stt_model": self.stt_model.currentText()}
        self.owner.store.save_config(self.owner.config)
        self.owner.select_character(self.owner.config["speech_voice"])
        self.owner.apply_theme(self.owner.config["theme"])
        return True

    def reject(self):
        if (self.worker and self.worker.isRunning()) or self.updates.running():
            self.status.setText("Wait for the current operation to finish before closing Settings.")
            self.updates.status.setText("Wait for the current operation to finish before closing Settings.")
            return
        self.owner.apply_theme(self.original_theme)
        self.owner.stop_speaking()
        super().reject()


class MessageCard(QFrame):
    def __init__(self, label, text, owner, actions=False):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        name = QLabel(label)
        name.setObjectName("badge")
        layout.addWidget(name)
        self.body = SafeBrowser()
        self.body.setMinimumHeight(70)
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.body.anchorClicked.connect(lambda url: owner.approve_link(url.toString()))
        layout.addWidget(self.body)
        self.set_text(text)
        if actions:
            for action in proposals(text):
                b = button("Review action · " + action["type"].replace("_", " "),
                           lambda checked=False, a=action: owner.review_action(a))
                owner.action_buttons.append(b)
                layout.addWidget(b)

    def set_text(self, text):
        self.body.setMarkdown(text)
        self.body.document().setTextWidth(max(360, self.body.viewport().width() - 20))
        height = int(self.body.document().size().height()) + 22
        self.body.setFixedHeight(min(1100, max(70, height)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.body.document().setTextWidth(max(250, self.body.viewport().width() - 20))
        self.body.setFixedHeight(min(1100, max(70, int(self.body.document().size().height()) + 22)))


class Window(QMainWindow):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or Store()
        self.config = self.store.config()
        legacy_voice = self.config.get("speech_voice")
        if "speech_voice" in self.config and legacy_voice != character_for(legacy_voice).selection:
            self.config["speech_voice"] = DEFAULT_CLOUD_VOICE
            self.store.save_config(self.config)
        self.pending_character = character_for(self.config.get("speech_voice"))
        self.speech_jobs = []
        self.speech_generation = 0
        self.cloud_speech_consent = False
        self.audio_player = None
        self.audio_buffer = None
        self.apply_theme(self.config.get("theme", "Night"))
        self.keys = {}
        self.key_warning = False
        for name in ("Gemini", "Groq"):
            try:
                self.keys[name] = get_key(name)
            except Exception:
                self.keys[name] = os.environ.get(name.upper() + "_API_KEY", "")
                self.key_warning = True
        self.chat = new_chat()
        self.project_root = None
        self.worker = None
        self.action_buttons = []
        self.partial_card = None
        self.partial = ""
        self.consent = set()
        self.events = []
        self.setWindowTitle("Kareem AI · Gemini + Groq")
        self.resize(1320, 860)
        self.setMinimumSize(990, 660)
        root = QSplitter()
        self.setCentralWidget(root)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 24, 18, 20)
        brand = QLabel("◈  Kareem AI")
        brand.setObjectName("brand")
        side.addWidget(brand)
        subtitle = QLabel("YOUR CLOUD WORKSPACE")
        subtitle.setObjectName("muted")
        side.addWidget(subtitle)
        side.addSpacing(22)
        self.new_button = button("＋  New conversation", self.start_chat, True)
        side.addWidget(self.new_button)
        self.chat_list = QListWidget()
        self.chat_list.itemClicked.connect(self.select_chat)
        side.addWidget(self.chat_list, 1)
        self.folder_button = button("Choose project folder", self.choose_folder)
        side.addWidget(self.folder_button)
        self.folder_label = QLabel("No folder access granted")
        self.folder_label.setObjectName("muted")
        self.folder_label.setWordWrap(True)
        side.addWidget(self.folder_label)
        self.settings_button = button("⚙  Settings", self.settings)
        side.addWidget(self.settings_button)
        root.addWidget(sidebar)
        middle = QWidget()
        main = QVBoxLayout(middle)
        main.setContentsMargins(26, 22, 26, 20)
        header = QHBoxLayout()
        heading = QLabel("Make something great.")
        heading.setObjectName("headline")
        header.addWidget(heading, 1)
        self.mode = QComboBox()
        self.mode.addItems(["Merge", "Gemini", "Groq"])
        self.character_choice = QComboBox()
        self.character_choice.setAccessibleName("Active character")
        for character in CHARACTERS:
            self.character_choice.addItem(character.name + " · " + character.title, character.selection)
        self.character_choice.setCurrentIndex(self.character_choice.findData(
            character_for(self.config.get("speech_voice")).selection))
        header.addWidget(self.character_choice)
        header.addWidget(self.mode)
        main.addLayout(header)
        self.character_badge = QLabel(character_for(self.config.get("speech_voice")).summary)
        self.character_badge.setObjectName("badge")
        self.character_badge.setWordWrap(True)
        main.addWidget(self.character_badge)
        self.character_choice.currentIndexChanged.connect(lambda _: self.select_character(
            self.character_choice.currentData()))
        notice = QLabel("Merge: two independent drafts → one combined answer · up to 3 API requests")
        notice.setObjectName("muted")
        notice.setWordWrap(True)
        main.addWidget(notice)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.messages_widget = QWidget()
        self.messages = QVBoxLayout(self.messages_widget)
        self.messages.setContentsMargins(0, 16, 0, 16)
        self.messages.setSpacing(14)
        self.messages.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.messages_widget)
        main.addWidget(self.scroll, 1)
        self.status = QLabel("Ready · Your PC runs the interface. AI processing happens in the cloud.")
        self.status.setObjectName("badge")
        self.status.setWordWrap(True)
        main.addWidget(self.status)
        self.composer = QPlainTextEdit()
        self.composer.setPlaceholderText("Ask a question, build an idea, or request a file edit…")
        self.composer.setFixedHeight(108)
        main.addWidget(self.composer)
        bottom = QHBoxLayout()
        caption = QLabel("Tool actions need your approval.")
        caption.setObjectName("muted")
        bottom.addWidget(caption, 1)
        self.voice_button = button("Voice", self.voice_mode)
        bottom.addWidget(self.voice_button)
        self.speak_button = button("Read aloud", self.read_latest)
        bottom.addWidget(self.speak_button)
        self.quiet_button = button("Mute", self.stop_speaking)
        bottom.addWidget(self.quiet_button)
        self.stop_button = button("Stop", self.stop)
        self.stop_button.setEnabled(False)
        bottom.addWidget(self.stop_button)
        self.send_button = button("Send  ↑", self.send, True)
        bottom.addWidget(self.send_button)
        main.addLayout(bottom)
        root.addWidget(middle)
        right = QWidget()
        rail = QVBoxLayout(right)
        rail.setContentsMargins(16, 24, 16, 20)
        rail.addWidget(QLabel("ACTIVITY"))
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumBlockCount(2000)
        rail.addWidget(self.activity, 1)
        self.drafts_button = button("View model contributions", self.show_drafts)
        rail.addWidget(self.drafts_button)
        self.export_button = button("Export conversation", self.export_chat)
        rail.addWidget(self.export_button)
        root.addWidget(right)
        root.setSizes([230, 780, 300])
        self.refresh_chats()
        self.render()
        if self.key_warning:
            self.log("Windows credential storage is unavailable. Session keys or environment variables can still be used.")

    def log(self, event):
        # Do not store keys even if a future error accidentally contains one.
        for key in self.keys.values():
            if key:
                event = event.replace(key, "[REDACTED]")
        entry = datetime.now().strftime("%H:%M:%S") + "  " + event
        self.events.append(entry)
        self.activity.appendPlainText(entry)
        self.store.log(self.chat["id"], event)

    def refresh_chats(self):
        self.chat_list.clear()
        for chat in self.store.chats():
            item = QListWidgetItem(chat["title"])
            item.setData(Qt.ItemDataRole.UserRole, chat)
            self.chat_list.addItem(item)

    def start_chat(self):
        if self.busy():
            return
        self.stop_speaking()
        self.chat = new_chat()
        self.events = []
        self.activity.clear()
        self.render()

    def select_chat(self, item):
        if self.busy():
            return
        self.stop_speaking()
        self.chat = item.data(Qt.ItemDataRole.UserRole)
        self.activity.clear()
        self.events = []
        self.render()
        self.log("Opened saved conversation. No API request sent.")

    def render(self):
        while self.messages.count():
            widget = self.messages.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self.action_buttons = []
        if not self.chat["messages"]:
            self.messages.addWidget(MessageCard("WELCOME, KAREEM", "## Two AIs. One place to create.\n"
                "Connect your **Gemini** and **Groq** keys in **Settings → Models & keys**, choose models available on "
                "your free accounts, then send a message.\n\n"
                "**Merge** combines their answers. Switch to one provider to save requests.\n\n"
                "Try: *Create a small Python game and propose saving it as game.py.*\n\n"
                "File and code actions always need your approval. API keys are never part of the conversation.", self))
        for message in self.chat["messages"]:
            label = "YOU" if message["role"] == "user" else message.get("label", "KAREEM AI")
            self.messages.addWidget(MessageCard(label, message["content"], self,
                                                 actions=message["role"] == "assistant"))
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def busy(self):
        return self.worker is not None and self.worker.isRunning()

    def set_busy(self, value):
        for control in [self.send_button, self.new_button, self.settings_button, self.folder_button,
                        self.mode, self.character_choice, self.chat_list, self.export_button, self.voice_button, self.speak_button, *self.action_buttons]:
            control.setEnabled(not value)
        self.stop_button.setEnabled(value)

    def settings(self):
        self.stop_speaking()
        Settings(self).exec()

    def apply_theme(self, name):
        QApplication.instance().setStyleSheet(stylesheet(STYLE, name))

    def select_character(self, selection):
        character = character_for(selection)
        self.stop_speaking()
        self.config["speech_voice"] = character.selection
        self.store.save_config(self.config)
        self.character_choice.blockSignals(True)
        self.character_choice.setCurrentIndex(self.character_choice.findData(character.selection))
        self.character_choice.blockSignals(False)
        self.character_badge.setText(character.summary)

    def stop_speaking(self):
        self.speech_generation += 1
        for worker in self.speech_jobs:
            if worker.isRunning():
                worker.cancel.set()
        if self.audio_player is not None:
            self.audio_player.stop()
            self.audio_player.deleteLater()
            self.audio_player = None
        if self.audio_buffer is not None:
            self.audio_buffer.close()
            self.audio_buffer.deleteLater()
            self.audio_buffer = None

    def speech_active(self):
        return any(worker.isRunning() for worker in self.speech_jobs)

    def cloud_say(self, text, selection, rate):
        self.stop_speaking()
        if not self.keys.get("Groq"):
            QMessageBox.information(self, "Groq key needed", "Save your Groq API key in Settings → Models & keys before previewing or using cloud voices.")
            return
        if not self.cloud_speech_consent:
            if QMessageBox.question(self, "Allow cloud speech this session?",
                "Generate spoken replies and voice previews with Groq for this session?\n\n"
                "This sends the text being spoken to Groq, including automatic readout if enabled. "
                "Each readout sends up to roughly 1,000 characters using at most 5 API requests. "
                "Your free quota/model access applies; accounts with paid billing may incur charges. "
                "The app does not enable billing. Mute cancels requests still in progress.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            self.cloud_speech_consent = True
        generation = self.speech_generation
        key = self.keys["Groq"]
        worker = Worker(lambda w: synthesize(text, key, selection, w.event.emit))
        self.speech_jobs.append(worker)
        worker.event.connect(self.log)
        worker.success.connect(lambda result: self.cloud_audio_ready(result, generation, rate))
        worker.failure.connect(lambda message: self.cloud_voice_failed(message, generation))
        worker.finished.connect(lambda: self.speech_finished(worker))
        self.status.setText("Generating Groq cloud voice…")
        self.log("Approved cloud speech using " + selection.split("|")[-1] + ".")
        worker.start()

    def speech_finished(self, worker):
        if worker in self.speech_jobs:
            self.speech_jobs.remove(worker)
        worker.deleteLater()

    def cloud_voice_failed(self, message, generation):
        if generation == self.speech_generation:
            self.status.setText(message)
        self.log(message)

    def cloud_audio_ready(self, result, generation, rate):
        if generation != self.speech_generation:
            return
        from PySide6.QtCore import QBuffer, QIODevice
        from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices, QtAudio
        try:
            pcm, sample_rate, channels, width = pcm_audio(result.audio)
        except ProviderError as exc:
            self.cloud_voice_failed(str(exc), generation)
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(sample_rate)
        fmt.setChannelCount(channels)
        fmt.setSampleFormat({1: QAudioFormat.SampleFormat.UInt8, 2: QAudioFormat.SampleFormat.Int16,
                             4: QAudioFormat.SampleFormat.Int32}[width])
        device = QMediaDevices.defaultAudioOutput()
        if device.isNull() or not device.isFormatSupported(fmt):
            self.cloud_voice_failed("Your output device cannot play this speech format. Choose another output device in Windows sound settings.", generation)
            return
        self.audio_player = QAudioSink(device, fmt, self)
        self.audio_player.stateChanged.connect(self.audio_playback_state)
        self.audio_buffer = QBuffer(self)
        self.audio_buffer.setData(pcm)
        self.audio_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.audio_player.start(self.audio_buffer)
        self.status.setText("Playing Groq cloud voice" + (" · Long reply shortened for quota" if result.truncated else ""))
        self.log(f"Cloud speech ready: {result.requests} request(s), {result.characters} characters. " +
                 ("Readout shortened to protect quota." if result.truncated else "Audio kept in memory only."))

    @Slot()
    def audio_playback_state(self):
        # A no-argument Qt slot also supports bindings that expose the legacy
        # QAudio::State signal name alongside QtAudio.State.
        from PySide6.QtMultimedia import QtAudio
        if self.audio_player is None:
            return
        if self.audio_player.error() != QtAudio.Error.NoError:
            self.status.setText("Cloud speech playback failed. Check your output device.")
        elif self.audio_player.state() == QtAudio.State.IdleState:
            self.status.setText("Ready · Cloud speech finished")

    def say(self, text, voice_name=None):
        selection = character_for(self.config.get("speech_voice") if voice_name is None else voice_name).selection
        self.cloud_say(text, selection, 0)

    def read_latest(self):
        message = next((m for m in reversed(self.chat["messages"]) if m["role"] == "assistant"), None)
        if message:
            self.say(message["content"])
        else:
            self.status.setText("Send a message first, then use Read aloud.")

    def voice_mode(self):
        if not self.busy():
            self.stop_speaking()
            VoiceDialog(self, Worker).exec()

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose the only folder file tools may access")
        if path:
            self.project_root = path
            self.folder_label.setText(path)
            self.log("Selected a project folder. Each read and change still needs approval.")

    def approve_link(self, url):
        if self.busy():
            return
        self.review_action({"type": "open_url", "url": url})

    def send(self):
        if self.busy():
            return
        self.stop_speaking()
        text = self.composer.toPlainText().strip()
        if not text:
            return
        if len(text) > 16000:
            QMessageBox.information(self, "Message too long", "Keep each message under 16,000 characters.")
            return
        mode = self.mode.currentText()
        names = ["Gemini", "Groq"] if mode == "Merge" else [mode]
        if any(not self.keys[n] or not self.config.get(n) for n in names):
            self.settings()
            if any(not self.keys[n] or not self.config.get(n) for n in names):
                return
        if mode not in self.consent:
            explanation = ("Merge sends this conversation to both Google Gemini and Groq, then sends both drafts "
                           "to Gemini for synthesis. That is up to 3 API requests."
                           if mode == "Merge" else f"This conversation will be sent to {mode} for a reply.")
            explanation += "\n\nProvider data policies and account quotas apply. The app cannot verify free-tier billing. Continue?"
            if QMessageBox.question(self, "Cloud processing", explanation,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            self.consent.add(mode)
        self.chat["messages"].append({"role": "user", "content": text})
        if len(self.chat["messages"]) == 1:
            self.chat["title"] = text[:45].replace("\n", " ")
        self.store.save_chat(self.chat)
        self.refresh_chats()
        self.composer.clear()
        self.render()
        self.partial = ""
        self.partial_card = MessageCard("WORKING · " + character_for(self.config.get("speech_voice")).name.upper(), "Thinking…", self)
        self.messages.addWidget(self.partial_card)
        history = [{"role": m["role"], "content": m["content"]} for m in self.chat["messages"]]
        self.pending_character = character_for(self.config.get("speech_voice"))
        engine = Engine({n: Provider(n, self.keys[n], self.config[n]) for n in names},
                        character=self.pending_character.selection)
        self.worker = Worker(lambda worker: engine.run(history, mode, worker.event.emit, worker.token.emit))
        self.worker.event.connect(self.log)
        self.worker.token.connect(self.receive_token)
        self.worker.success.connect(lambda result: self.answer_ready(result, mode))
        self.worker.failure.connect(self.failed)
        self.worker.finished.connect(self.finished)
        self.set_busy(True)
        self.status.setText("Thinking in the cloud…")
        self.worker.start()

    def receive_token(self, chunk):
        self.partial += chunk
        if self.partial_card:
            # Plain text while streaming prevents repeated Markdown parsing on large drafts.
            self.partial_card.body.setPlainText(self.partial)

    def answer_ready(self, answer: Answer, mode):
        label = self.pending_character.name.upper() + " · " + mode.upper() + (" · SINGLE DRAFT / MERGE UNAVAILABLE" if answer.degraded else "")
        self.chat["messages"].append({"role": "assistant", "content": answer.text, "label": label,
                                       "character": self.pending_character.selection})
        self.chat.setdefault("runs", []).append({"mode": mode, "character": self.pending_character.selection, "drafts": answer.drafts,
                                                 "usage": answer.usage, "degraded": answer.degraded})
        self.store.save_chat(self.chat)
        self.partial_card = None
        self.render()
        # Signal arrives before QThread.finished; keep new action buttons disabled until then.
        self.set_busy(True)
        self.refresh_chats()
        self.log("Answer ready. " + ("Provider token usage recorded." if answer.usage else
                                    "Token totals were not returned by the streaming API; no estimate invented."))
        self.status.setText("Ready · " + label)
        if self.config.get("read_replies", False):
            self.say(answer.text, self.pending_character.selection)

    def failed(self, message):
        self.log(message)
        self.partial_card = None
        self.render()
        self.set_busy(True)
        self.status.setText(message)
        # Failed replies are never stored as successful answers or offered as actions.
        self.log("Your message was saved. You can switch provider or send a follow-up when ready.")

    def finished(self):
        self.set_busy(False)

    def stop(self):
        if self.busy():
            self.worker.cancel.set()
            self.stop_button.setEnabled(False)
            self.status.setText("Stopping…")

    def review_action(self, action):
        if self.busy():
            return
        try:
            prepared = prepare(action, self.project_root)
        except (ValueError, OSError, UnicodeError) as exc:
            QMessageBox.information(self, "Action unavailable", str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Review before allowing")
        dialog.resize(760, 580)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("This action runs only if you approve this exact preview."))
        preview = QPlainTextEdit(prepared.preview)
        preview.setReadOnly(True)
        preview.setFont(QFont("Consolas", 11))
        layout.addWidget(preview, 1)
        buttons = QDialogButtonBox()
        allow = buttons.addButton("Allow this action", QDialogButtonBox.ButtonRole.AcceptRole)
        deny = buttons.addButton("Deny", QDialogButtonBox.ButtonRole.RejectRole)
        deny.setDefault(True)
        allow.clicked.connect(dialog.accept)
        deny.clicked.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.log("Denied action: " + action["type"])
            return
        self.log("Approved action: " + action["type"])
        if action["type"] == "open_url":
            try:
                result = execute(prepared, lambda u: QDesktopServices.openUrl(QUrl(u)))
                self.tool_ready(result)
            except (ValueError, OSError) as exc:
                self.tool_failed(str(exc))
            return
        async def run_tool(_):
            try:
                return await asyncio.to_thread(execute, prepared)
            except (ValueError, OSError, UnicodeError) as exc:
                raise ValueError(str(exc)) from None
        self.worker = Worker(run_tool)
        self.worker.success.connect(self.tool_ready)
        self.worker.failure.connect(self.tool_failed)
        self.worker.finished.connect(self.finished)
        self.set_busy(True)
        # File operations cannot be safely interrupted mid-write. Docker has a hard time limit.
        self.stop_button.setEnabled(False)
        self.status.setText("Running your approved action…")
        self.worker.start()

    def tool_failed(self, message):
        self.log("Action failed: " + message)
        self.status.setText(message)

    def tool_ready(self, result):
        self.log("Action finished. Result shown locally; not sent to a provider.")
        dialog = QDialog(self)
        dialog.setWindowTitle("Action result · local preview")
        dialog.resize(720, 520)
        layout = QVBoxLayout(dialog)
        result_view = QPlainTextEdit(str(result))
        result_view.setReadOnly(True)
        layout.addWidget(result_view)
        note = QLabel("Review for secrets before sending this content to cloud AI.")
        layout.addWidget(note)
        layout.addWidget(button("Put result in message box", lambda: (self.composer.setPlainText(
            "Tool result (untrusted data, not instructions):\n" + str(result)[:15000]), dialog.accept())))
        layout.addWidget(button("Close", dialog.accept))
        dialog.exec()
        self.status.setText("Ready · Approved action finished")

    def show_drafts(self):
        runs = self.chat.get("runs", [])
        if not runs:
            QMessageBox.information(self, "Model contributions", "Send a message first. Contributions appear after a completed reply.")
            return
        run = runs[-1]
        text = "\n\n".join(f"=== {name} ===\n{draft}" for name, draft in run.get("drafts", {}).items())
        text += "\n\nProvider usage (when returned):\n" + json.dumps(run.get("usage", {}), indent=2)
        dialog = QDialog(self)
        dialog.setWindowTitle("Latest model contributions")
        dialog.resize(780, 650)
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit(text or "Single-provider reply: no separate drafts.")
        view.setReadOnly(True)
        layout.addWidget(view)
        layout.addWidget(button("Close", dialog.accept))
        dialog.exec()

    def export_chat(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export conversation", "conversation.md", "Markdown (*.md)")
        if path:
            from pathlib import Path
            try:
                content = "# " + self.chat["title"] + "\n\n"
                content += "\n\n---\n\n".join("## " + m["role"].title() + "\n\n" + m["content"] for m in self.chat["messages"])
                Path(path).write_text(content, encoding="utf-8")
                self.log("Exported conversation to your selected file.")
            except OSError:
                QMessageBox.information(self, "Export failed", "Couldn't write to that location.")

    def closeEvent(self, event):
        if self.speech_active():
            self.stop_speaking()
            self.status.setText("Stopping cloud voice… Close again once it finishes.")
            event.ignore()
        elif self.busy():
            self.status.setText("Wait for the action to finish, or stop the AI reply before closing.")
            event.ignore()
        else:
            self.stop_speaking()
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Kareem AI")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
