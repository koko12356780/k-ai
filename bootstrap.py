"""Stable launcher: prefer an installed release while keeping chat history separate."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def installed_root(source_root, data_root):
    try:
        version = json.loads((data_root / "current.json").read_text(encoding="utf-8"))["version"]
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            return source_root
        releases = (data_root / "releases").resolve()
        target = (releases / version).resolve(strict=True)
        manifest = json.loads((target / "bundle.json").read_text(encoding="utf-8"))
        if target.parent == releases and manifest.get("version") == version and (target / "kareem_ai" / "app.py").is_file():
            return target
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return source_root


def main():
    source = Path(__file__).resolve().parent
    override = os.environ.get("KAREEM_AI_DATA_DIR")
    data = Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "KareemAI"
    target = installed_root(source, data)
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
    subprocess.Popen([sys.executable, "-m", "kareem_ai"], cwd=target, **flags)


if __name__ == "__main__":
    main()
