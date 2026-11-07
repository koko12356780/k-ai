"""Build a curated source release without user files, keys, environments, or caches."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def build(destination=None):
    root = Path(__file__).resolve().parent
    version = json.loads((root / "bundle.json").read_text(encoding="utf-8"))["version"]
    from kareem_ai import __version__
    from kareem_ai.updates import version_tuple
    version_tuple(version)
    if version != __version__:
        raise ValueError("bundle.json and application versions must match")
    output = Path(destination) if destination else root / "dist"
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"Kareem-AI-v{version}.zip"
    files = [root / name for name in ("README.md", "requirements.txt", "Launch Kareem AI.bat",
             "bootstrap.py", "bundle.json", "build_release.py", "RELEASE-NOTES.md", "TEST-RESULTS.md")]
    files += list((root / "kareem_ai").glob("*.py")) + list((root / "tests").glob("test_*.py"))
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, "kareem-ai/" + path.relative_to(root).as_posix())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (output / (target.name + ".sha256")).write_text(digest + "  " + target.name + "\n", encoding="utf-8")
    print(target)
    print("SHA-256: " + digest)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    build(parser.parse_args().output)
