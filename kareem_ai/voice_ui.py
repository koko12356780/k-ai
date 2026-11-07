from __future__ import annotations

import time

from PySide6.QtCore import QBuffer, QIODevice, QTimer, Slot
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox,
                              QPlainTextEdit, QPushButton, QVBoxLayout)

from .voice import MAX_AUDIO_BYTES, transcribe, wav_audio, voice_id
from .cloud_voice import CLOUD_VOICES, DEFAULT_CLOUD_VOICE, is_cloud_voice, voice_setup_url


class VoiceDialog(QDialog):
    def __init__(self, owner, worker_class):
        super().__init__(owner)
        self.owner = owner
        self.worker_class = worker_class
        self.worker = None
        self.source = None
        self.buffer = None
        self.audio = b""
        self.format = None
        self.started_at = 0
        self.setWindowTitle("Voice mode · push to talk")
        self.resize(650, 560)
        layout = QVBoxLayout(self)
        title = QLabel("Say it. Review it. Send it.")
        title.setObjectName("headline")
        layout.addWidget(title)
        note = QLabel("The microphone is off until you press Record. Stop after speaking, then choose\n"
                      "Transcribe to send that recording to Groq. Review the text before using it.\n"
                      "Audio stays in memory and is discarded when you close this window. Maximum: 60 seconds.")
        note.setWordWrap(True)
        layout.addWidget(note)
        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("Reply voice"))
        self.reply_voice = QComboBox()
        for label, selection in CLOUD_VOICES:
            self.reply_voice.addItem(label, selection)
        self.reply_voice.addItem("Windows · Default voice", "")
        for voice in owner.voice_options():
            self.reply_voice.addItem("Windows · " + voice.name() + " · " + voice.locale().name(), voice_id(voice))
        saved = owner.config.get("speech_voice", DEFAULT_CLOUD_VOICE)
        selected = self.reply_voice.findData(saved)
        if selected < 0:
            selected = next((i for i in range(self.reply_voice.count())
                             if self.reply_voice.itemData(i).endswith("|" + saved)), -1)
        if selected < 0 and saved:
            self.reply_voice.addItem("Unavailable saved voice · " + saved, saved)
            selected = self.reply_voice.count() - 1
        self.reply_voice.setCurrentIndex(max(0, selected))
        voice_row.addWidget(self.reply_voice, 1)
        self.preview_voice = QPushButton("Try this voice")
        self.preview_voice.clicked.connect(lambda: owner.say(
            "Hey Kareem! I'm ready to help. How does this voice sound?", self.reply_voice.currentData() or ""))
        voice_row.addWidget(self.preview_voice)
        save_voice = QPushButton("Save voice")
        save_voice.clicked.connect(self.save_voice)
        voice_row.addWidget(save_voice)
        layout.addLayout(voice_row)
        cloud_note = QLabel("Groq voices generate speech in the cloud using your key and quota. Windows voices stay local.")
        cloud_note.setWordWrap(True)
        layout.addWidget(cloud_note)
        setup = QPushButton("Groq voice setup ↗ · review model terms in your account")
        setup.clicked.connect(lambda: owner.approve_link(voice_setup_url(self.reply_voice.currentData()))
                              if is_cloud_voice(self.reply_voice.currentData()) else None)
        layout.addWidget(setup)
        self.devices = QMediaDevices.audioInputs()
        self.device = QComboBox()
        self.device.addItems([d.description() for d in self.devices])
        self.device.setCurrentIndex(next((i for i, d in enumerate(self.devices)
                                         if d == QMediaDevices.defaultAudioInput()), 0))
        layout.addWidget(self.device)
        row = QHBoxLayout()
        self.record = QPushButton("● Record")
        self.record.setObjectName("primary")
        self.record.clicked.connect(self.start_recording)
        self.stop = QPushButton("■ Stop recording")
        self.stop.clicked.connect(self.stop_recording)
        self.stop.setEnabled(False)
        self.upload = QPushButton("Transcribe with Groq")
        self.upload.clicked.connect(self.upload_audio)
        self.upload.setEnabled(False)
        for widget in (self.record, self.stop, self.upload):
            row.addWidget(widget)
        layout.addLayout(row)
        self.status = QLabel("Microphone off")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.transcript = QPlainTextEdit()
        self.transcript.setPlaceholderText("Your editable transcript appears here. Nothing is automatically sent as a chat message.")
        layout.addWidget(self.transcript, 1)
        self.use = QPushButton("Use transcript in message box")
        self.use.setEnabled(False)
        self.use.clicked.connect(self.use_transcript)
        self.transcript.textChanged.connect(lambda: self.use.setEnabled(bool(self.transcript.toPlainText().strip()) and not self.running()))
        layout.addWidget(self.use)
        close = QPushButton("Close / discard recording")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.tick)
        if not self.devices:
            self.record.setEnabled(False)
            self.status.setText("No microphone found. Connect one and reopen Voice mode.")

    def running(self):
        return self.worker is not None and self.worker.isRunning()

    def save_voice(self):
        self.owner.config["speech_voice"] = self.reply_voice.currentData() or ""
        self.owner.store.save_config(self.owner.config)
        self.status.setText("Reply voice saved. Use Try this voice to hear it.")

    def start_recording(self):
        if not self.devices or self.running():
            return
        if QMessageBox.question(self, "Allow microphone recording?",
            "Record from the selected microphone for up to 60 seconds?\n"
            "It stays local until you separately choose Transcribe with Groq.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.owner.stop_speaking()
        device = self.devices[self.device.currentIndex()]
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt.setSampleRate(device.preferredFormat().sampleRate())
            fmt.setChannelCount(device.preferredFormat().channelCount())
        if not device.isFormatSupported(fmt):
            self.status.setText("This microphone does not support 16-bit PCM. Choose another input device.")
            return
        self.audio = b""
        self.transcript.clear()
        self.format = fmt
        self.buffer = QBuffer(self)
        self.buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self.source = QAudioSource(device, fmt, self)
        self.source.stateChanged.connect(self.audio_state)
        self.source.start(self.buffer)
        if self.source is None:
            return
        self.started_at = time.monotonic()
        self.record.setEnabled(False)
        self.preview_voice.setEnabled(False)
        self.device.setEnabled(False)
        self.stop.setEnabled(True)
        self.upload.setEnabled(False)
        self.use.setEnabled(False)
        self.status.setText("● Recording · 0 seconds")
        self.timer.start()
        self.owner.log("Microphone recording approved and started. No audio uploaded.")

    @Slot()
    def audio_state(self):
        if self.source is not None and self.source.error().value != 0:
            self.stop_recording()
            self.status.setText("Microphone capture failed. Check Windows microphone permissions and your input device.")

    def tick(self):
        if self.source is None:
            return
        elapsed = time.monotonic() - self.started_at
        self.status.setText(f"● Recording · {int(elapsed)} / 60 seconds")
        if elapsed >= 60 or self.buffer.size() >= MAX_AUDIO_BYTES:
            self.stop_recording()

    def stop_recording(self):
        self.timer.stop()
        source, self.source = self.source, None
        if source is not None:
            source.stop()
            source.deleteLater()
        if self.buffer is not None:
            pcm = bytes(self.buffer.data())[:MAX_AUDIO_BYTES]
            self.buffer.close()
            self.buffer.deleteLater()
            self.buffer = None
            try:
                self.audio = wav_audio(pcm, self.format.sampleRate(), self.format.channelCount())
                self.status.setText("Recording ready locally. Transcribe sends it to Groq; free account quotas apply.")
            except ValueError as exc:
                self.audio = b""
                self.status.setText(str(exc))
        self.record.setEnabled(bool(self.devices))
        self.preview_voice.setEnabled(True)
        self.device.setEnabled(True)
        self.stop.setEnabled(False)
        self.upload.setEnabled(bool(self.audio))
        self.use.setEnabled(bool(self.transcript.toPlainText().strip()))

    def upload_audio(self):
        if not self.audio or self.running():
            return
        if not self.owner.keys.get("Groq"):
            self.status.setText("Add your Groq key in Settings, then reopen Voice mode.")
            return
        if QMessageBox.question(self, "Send recording to Groq?",
            "Send this microphone recording to Groq's speech-to-text API?\n"
            "This uses your Groq account's transcription quota. The transcript will be shown for review.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.status.setText("Transcribing with Groq…")
        self.owner.log("Approved sending one recording to Groq for transcription.")
        self.record.setEnabled(False)
        self.upload.setEnabled(False)
        self.use.setEnabled(False)
        audio = self.audio
        self.worker = self.worker_class(lambda _: transcribe(audio, self.owner.keys["Groq"],
            self.owner.config.get("stt_model", "whisper-large-v3-turbo")))
        self.worker.success.connect(self.received)
        self.worker.failure.connect(self.failed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def received(self, text):
        self.transcript.setPlainText(text)
        self.status.setText("Review or edit your transcript, then put it in the message box.")
        self.owner.log("Voice transcript received. It has not been sent as a chat message.")

    def failed(self, message):
        self.status.setText(message)
        self.owner.log(message)

    def finished(self):
        self.record.setEnabled(bool(self.devices))
        self.upload.setEnabled(bool(self.audio))
        self.use.setEnabled(bool(self.transcript.toPlainText().strip()))

    def use_transcript(self):
        text = self.transcript.toPlainText().strip()
        if text and not self.running() and self.source is None:
            previous = self.owner.composer.toPlainText().rstrip()
            self.owner.composer.setPlainText((previous + "\n" if previous else "") + text)
            self.reject()

    def reject(self):
        if self.running():
            self.worker.cancel.set()
            self.status.setText("Cancelling transcription… Close again when it finishes.")
            return
        self.stop_recording()
        self.owner.stop_speaking()
        self.audio = b""
        super().reject()
