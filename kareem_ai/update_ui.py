from __future__ import annotations

import asyncio
import os
import subprocess
import sys

from PySide6.QtWidgets import QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from . import __version__
from .updates import (RELEASE_PAGE, REPOSITORY, activate, download_release, install_bundle,
                      latest_release, version_tuple)


class UpdatePanel(QWidget):
    def __init__(self, owner, worker_class, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.worker_class = worker_class
        self.worker = None
        self.release = None
        self.staged = None
        layout = QVBoxLayout(self)
        title = QLabel("Updates, when you choose.")
        title.setObjectName("headline")
        layout.addWidget(title)
        layout.addWidget(QLabel(f"Installed version: {__version__}\nUpdate source: github.com/{REPOSITORY}"))
        note = QLabel("Check for a new release, review its notes, then approve installation.\n"
                      "Your conversations and API keys stay separate from app updates.\n"
                      "Only this GitHub repository supplies updates. No background installs.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.check = QPushButton("Check for updates")
        self.check.clicked.connect(self.check_updates)
        layout.addWidget(self.check)
        self.status = QLabel("Click Check for updates to contact GitHub.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setPlaceholderText("Release notes appear here.")
        layout.addWidget(self.notes, 1)
        self.install = QPushButton("Download & install update")
        self.install.setObjectName("primary")
        self.install.setEnabled(False)
        self.install.clicked.connect(self.install_update)
        layout.addWidget(self.install)
        self.restart = QPushButton("Restart into update")
        self.restart.setEnabled(False)
        self.restart.clicked.connect(self.restart_app)
        layout.addWidget(self.restart)
        page = QPushButton("Open GitHub release page ↗")
        page.clicked.connect(lambda: owner.approve_link(RELEASE_PAGE))
        layout.addWidget(page)

    def running(self):
        return self.worker is not None and self.worker.isRunning()

    def check_updates(self):
        if self.running():
            return
        self.release = None
        self.staged = None
        self.install.setEnabled(False)
        self.restart.setEnabled(False)
        self.check.setEnabled(False)
        self.status.setText("Checking GitHub releases…")
        self.worker = self.worker_class(lambda _: latest_release())
        self.worker.success.connect(self.checked)
        self.worker.failure.connect(self.failed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def checked(self, release):
        self.release = release
        self.notes.setPlainText(release.notes or "No release notes provided.")
        newer = version_tuple(release.version) > version_tuple(__version__)
        self.status.setText(f"Version {release.version} is available." if newer else "You're up to date.")
        target = self.owner.store.root.resolve() / "releases" / release.version
        if newer and target.is_dir():
            self.staged = target
            self.status.setText(f"Version {release.version} is already downloaded. Restart to use it.")
        self.owner.log("Checked GitHub updates: latest stable version " + release.version)

    def finished(self):
        self.check.setEnabled(True)
        self.install.setEnabled(bool(self.release) and not self.staged and
                                version_tuple(self.release.version) > version_tuple(__version__))
        self.restart.setEnabled(self.staged is not None)

    def failed(self, message):
        self.status.setText(message)
        self.owner.log("Update: " + message)

    def install_update(self):
        if not self.release or self.running() or version_tuple(self.release.version) <= version_tuple(__version__):
            return
        if QMessageBox.question(self, "Install this update?",
            f"Download version {self.release.version} from {REPOSITORY}?\n\n"
            "The app verifies GitHub's SHA-256 checksum and installs the release in a separate folder. "
            "Restart runs code published in that release. Your current app stays open until you choose Restart.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        release = self.release
        async def install(_):
            payload = await download_release(release)
            return await asyncio.to_thread(install_bundle, payload, release, self.owner.store.root)
        self.check.setEnabled(False)
        self.install.setEnabled(False)
        self.restart.setEnabled(False)
        self.status.setText("Downloading and verifying update…")
        self.owner.log("Approved downloading and installing version " + release.version)
        self.worker = self.worker_class(install)
        self.worker.success.connect(self.installed)
        self.worker.failure.connect(self.failed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def installed(self, target):
        self.staged = target
        self.status.setText("Update installed. Restart when you're ready; your chats and keys are preserved.")
        self.owner.log("Update verified and installed. Restart is waiting for your approval.")

    def restart_app(self):
        if self.running() or not self.staged or self.owner.busy():
            return
        if self.owner.speech_active():
            self.owner.stop_speaking()
            self.status.setText("Stopping cloud speech. Click Restart again when it finishes.")
            return
        if QMessageBox.question(self, "Restart now?", "Save your settings and restart into the downloaded update?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        # Parent Settings saves keys/preferences using its regular path before activation.
        if not self.parent_settings().save_for_restart():
            return
        try:
            activate(self.staged, self.owner.store.root)
            env = os.environ.copy()
            env["KAREEM_AI_DATA_DIR"] = str(self.owner.store.root.resolve())
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
            subprocess.Popen([sys.executable, "-m", "kareem_ai"], cwd=self.staged, env=env, **flags)
        except (OSError, ValueError):
            self.status.setText("Could not start the update. Your current app is still open. Check the installed release folder.")
            return
        self.owner.log("Restarting into the approved update.")
        self.parent_settings().accept()
        self.owner.close()

    def parent_settings(self):
        parent = self.parentWidget()
        while parent is not None and not hasattr(parent, "save_for_restart"):
            parent = parent.parentWidget()
        return parent
