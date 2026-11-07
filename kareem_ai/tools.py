from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


KINDS = {"list_files", "read_file", "write_file", "run_python", "open_url"}


def proposals(text):
    result = []
    for block in re.findall(r"```action\s*\n(.*?)```", text, re.DOTALL):
        try:
            action = json.loads(block)
            if isinstance(action, dict) and action.get("type") in KINDS:
                result.append(action)
        except ValueError:
            pass
    return result[:5]


@dataclass(frozen=True)
class Prepared:
    action: dict
    root: Path | None
    target: Path | None
    original: bytes | None
    preview: str


def safe_path(root: Path, value: str, writing=False):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("Invalid file path.")
    relative = Path(value)
    if relative.is_absolute() or relative.drive or ":" in value:
        raise ValueError("Use a path relative to the approved folder.")
    root = root.resolve(strict=True)
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError("That path leaves the approved folder.")
    # Reject links and Windows junctions, even when they point within the folder.
    cursor = root / relative
    while cursor != root:
        attributes = getattr(cursor.lstat(), "st_file_attributes", 0) if cursor.exists() else 0
        if cursor.is_symlink() or attributes & 0x400:
            raise ValueError("Linked folders and files are not supported.")
        if cursor.parent == cursor:
            raise ValueError("Invalid path.")
        cursor = cursor.parent
    protected = {"sources", ".git", ".codex", ".agents", ".aws"}
    if writing and any(part.lower() in protected for part in target.parts):
        raise ValueError("Reference and application metadata folders are read-only.")
    return target


def prepare(action, root=None):
    action = json.loads(json.dumps(action))
    kind = action.get("type")
    if kind not in KINDS:
        raise ValueError("Unsupported action.")
    target = None
    original = None
    if kind in {"read_file", "write_file", "list_files"}:
        if root is None:
            raise ValueError("Choose a project folder first.")
        root = Path(root).resolve(strict=True)
        target = safe_path(root, action.get("path", ""), kind == "write_file")
        if kind == "write_file":
            content = action.get("content")
            if not isinstance(content, str) or len(content.encode("utf-8")) > 200000:
                raise ValueError("File text must be smaller than 200 KB.")
            if target.exists():
                if target.stat().st_size > 200000:
                    raise ValueError("Existing file is too large to preview safely.")
                original = target.read_bytes()
            previous = original.decode("utf-8") if original is not None else ""
            diff = "".join(difflib.unified_diff(previous.splitlines(True), content.splitlines(True),
                                                fromfile=str(target), tofile="proposed version"))
            preview = f"Write file: {target}\n\n{diff or '(No text differences)'}"
        else:
            preview = f"{kind.replace('_', ' ').title()}: {target}\n\nResult stays here until you send it to the AI."
    elif kind == "run_python":
        code = action.get("code")
        if not isinstance(code, str) or len(code) > 50000:
            raise ValueError("Invalid or oversized Python program.")
        preview = "Run Python inside Docker, offline, with no project files mounted.\nTime: 15 seconds. Memory: 128 MB.\n\n" + code
    else:
        value = action.get("url", "")
        url = urlsplit(value)
        if (not isinstance(value, str) or len(value) > 4000 or any(ord(c) < 32 for c in value)
                or url.scheme != "https" or not url.hostname or url.username or url.password):
            raise ValueError("Only ordinary HTTPS links without embedded credentials are allowed.")
        preview = "Open this exact link in your browser?\n\n" + value + "\n\nThis may use your browser's signed-in session. No page content is read by the app."
    return Prepared(action, root, target, original, preview)


def execute(prepared, open_url=None):
    # Called only after the UI approves this specific immutable preview.
    action = prepared.action
    kind = action["type"]
    if prepared.target is not None:
        target = safe_path(prepared.root, action["path"], kind == "write_file")
        if target != prepared.target:
            raise ValueError("Path changed since preview. Request approval again.")
    if kind == "list_files":
        if not target.is_dir():
            raise ValueError("That path is not a folder.")
        entries = []
        for entry in target.iterdir():
            entries.append(entry.name + ("/" if entry.is_dir() else ""))
            if len(entries) >= 250:
                entries.append("[Stopped at 250 entries]")
                break
        return "\n".join(sorted(entries)) or "(Empty folder)"
    if kind == "read_file":
        if target.stat().st_size > 200000:
            raise ValueError("File exceeds 200 KB. Read a smaller text file.")
        return target.read_text(encoding="utf-8")[:16000]
    if kind == "write_file":
        now = target.read_bytes() if target.exists() else None
        if now != prepared.original:
            raise ValueError("File changed since preview. Request approval again.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(action["content"], encoding="utf-8")
        return f"Saved {action['path']} ({len(action['content'])} characters)."
    if kind == "open_url":
        if open_url is None or not open_url(action["url"]):
            raise ValueError("Could not open the browser.")
        return "Opened the approved link. The app has not read or interacted with the page."
    return run_python(action["code"])


def run_python(code):
    docker = shutil.which("docker")
    if not docker:
        raise ValueError("Code execution needs Docker Desktop and a local python:3.12-alpine image. No code was run on your PC.")
    name = "kareem-ai-" + uuid.uuid4().hex
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
    with tempfile.TemporaryDirectory(prefix="kareem-ai-") as temp:
        script = Path(temp) / "main.py"
        script.write_text(code, encoding="utf-8")
        command = [docker, "run", "--rm", "--pull=never", "--name", name, "--network=none",
                   "--read-only", "--memory=128m", "--cpus=0.5", "--pids-limit=32",
                   "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534",
                   "--log-driver=none", "--ulimit", "fsize=65536:65536",
                   "--mount", f"type=bind,source={script},target=/main.py,readonly",
                   "python:3.12-alpine", "python", "-I", "-B", "/main.py"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **flags)
        output = bytearray()
        exceeded = threading.Event()
        def drain():
            while True:
                chunk = process.stdout.read(1024)
                if not chunk:
                    break
                available = max(0, 16000 - len(output))
                output.extend(chunk[:available])
                if len(chunk) > available:
                    exceeded.set()
                # Always drain the pipe, but never keep more than 16 KB in host memory.
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        timed_out = False
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            try:
                subprocess.run([docker, "rm", "-f", name], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=10, **flags)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                reader.join(timeout=2)
        text = output.decode("utf-8", errors="replace")
        if timed_out:
            text += "\n[Stopped at the 15-second time limit]"
        if exceeded.is_set():
            text += "\n[Output truncated at 16 KB]"
        return f"Exit code: {process.returncode}\n{text}"
