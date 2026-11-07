"""Explicit, checksum-verified GitHub release updates; no in-place code replacement."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import httpx

from . import __version__
from .storage import write_json

REPOSITORY = "koko12356780/k-ai"
RELEASE_PAGE = f"https://github.com/{REPOSITORY}/releases"
MAX_DOWNLOAD = 20 * 1024 * 1024
MAX_EXTRACTED = 40 * 1024 * 1024


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise ValueError("Release version must use major.minor.patch, for example 0.2.0.")
    return tuple(map(int, value.removeprefix("v").split(".")))


@dataclass(frozen=True)
class Release:
    version: str
    notes: str
    url: str
    digest: str
    size: int


async def latest_release(transport=None):
    async with httpx.AsyncClient(transport=transport, timeout=25, follow_redirects=False) as client:
        try:
            response = await client.get(f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "KareemAI/" + __version__})
            if response.status_code == 404:
                raise ValueError("No published release yet. Your installed app still works.")
            if response.status_code in (403, 429):
                raise ValueError("GitHub's update-check limit was reached. Try again later.")
            response.raise_for_status()
            data = response.json()
            tag = data["tag_name"]
            version_tuple(tag)
            if data.get("draft") or data.get("prerelease"):
                raise ValueError("This channel accepts stable published releases only.")
            name = f"Kareem-AI-{tag}.zip"
            asset = next((a for a in data.get("assets", []) if a.get("name") == name), None)
            if asset is None:
                raise ValueError("The release package is not ready yet. Try again shortly.")
            expected = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
            digest = asset.get("digest", "")
            if asset.get("browser_download_url") != expected or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
                raise ValueError("Release download metadata is invalid or its SHA-256 checksum is missing.")
            size = asset.get("size", 0)
            if not isinstance(size, int) or not 0 < size <= MAX_DOWNLOAD:
                raise ValueError("Release package is too large or has an invalid size.")
            return Release(tag.removeprefix("v"), str(data.get("body", ""))[:20000], expected,
                           digest[7:], size)
        except (httpx.HTTPError, KeyError, TypeError):
            raise ValueError("Couldn't check GitHub releases. Check your connection and try again.") from None


async def download_release(release, transport=None):
    version_tuple(release.version)
    expected = f"https://github.com/{REPOSITORY}/releases/download/v{release.version}/Kareem-AI-v{release.version}.zip"
    if release.url != expected or not re.fullmatch(r"[a-f0-9]{64}", release.digest):
        raise ValueError("Unexpected update source or checksum.")
    allowed_hosts = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
    url = release.url
    async with httpx.AsyncClient(transport=transport, timeout=60, follow_redirects=False) as client:
        try:
            for _ in range(5):
                parsed = urlsplit(url)
                if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username or parsed.password or parsed.port not in (None, 443):
                    raise ValueError("Update download redirected outside trusted GitHub hosts.")
                async with client.stream("GET", url, headers={"User-Agent": "KareemAI/" + __version__}) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        from urllib.parse import urljoin
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    response.raise_for_status()
                    output = bytearray()
                    async for chunk in response.aiter_bytes():
                        output.extend(chunk)
                        if len(output) > min(MAX_DOWNLOAD, release.size):
                            raise ValueError("Update exceeded its declared size.")
                    if len(output) != release.size or hashlib.sha256(output).hexdigest() != release.digest:
                        raise ValueError("Update checksum/size did not match. Nothing was installed.")
                    return bytes(output)
            raise ValueError("Too many update download redirects.")
        except httpx.HTTPError:
            raise ValueError("Update download failed. No changes were made to the running app.") from None


def install_bundle(payload: bytes, release: Release, data_root: Path):
    if hashlib.sha256(payload).hexdigest() != release.digest or len(payload) != release.size:
        raise ValueError("The downloaded package failed verification.")
    version_tuple(release.version)
    releases = data_root.resolve() / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    if releases.is_symlink() or getattr(releases.stat(), "st_file_attributes", 0) & 0x400:
        raise ValueError("The release directory cannot be a linked folder.")
    target = releases / release.version
    if target.exists():
        raise ValueError("This version is already downloaded. Use Restart into update, or check the release folder.")
    stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=releases))
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) > 400 or sum(m.file_size for m in members) > MAX_EXTRACTED:
                raise ValueError("Update archive exceeds extraction limits.")
            names = set()
            for item in members:
                # ZipInfo normalizes backslashes on Windows; validate the original
                # archive name too, before trusting the normalized destination.
                raw = item.orig_filename
                parts = PurePosixPath(raw).parts
                if (raw != item.filename or "\x00" in raw or not parts or parts[0] != "kareem-ai" or PurePosixPath(raw).is_absolute()
                        or any(p in ("..", ".") or ":" in p or "\\" in p or p.rstrip(" .") != p
                               or p.lower() in {".git", "user-data", ".env", "chats", "sources"}
                               or p.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}
                               for p in parts)
                        or stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1):
                    raise ValueError("Update archive contains an unsafe path or link.")
                canonical = raw.rstrip("/").casefold()
                if canonical in names:
                    raise ValueError("Update archive contains duplicate paths.")
                names.add(canonical)
            required = {"kareem-ai/bundle.json", "kareem-ai/kareem_ai/__init__.py",
                        "kareem-ai/kareem_ai/app.py", "kareem-ai/kareem_ai/core.py",
                        "kareem-ai/bootstrap.py", "kareem-ai/requirements.txt"}
            if not required.issubset(names):
                raise ValueError("Update package is missing required application files.")
            manifest = json.loads(archive.read("kareem-ai/bundle.json"))
            if manifest.get("schema") != 1 or manifest.get("version") != release.version:
                raise ValueError("Update package version or format does not match the release.")
            # All members are validated before extraction. User history and keys are elsewhere.
            archive.extractall(stage)
        os.replace(stage / "kareem-ai", target)
        return target
    except (zipfile.BadZipFile, OSError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError("Couldn't install this update package. The running app was not changed.") from None
    finally:
        shutil.rmtree(stage)


def activate(target, data_root):
    target = Path(target).resolve(strict=True)
    root = Path(data_root).resolve(strict=True)
    if target.parent != root / "releases":
        raise ValueError("Update is outside this app's release folder.")
    version_tuple(target.name)
    manifest = json.loads((target / "bundle.json").read_text(encoding="utf-8"))
    if manifest.get("version") != target.name or not (target / "kareem_ai" / "app.py").is_file():
        raise ValueError("Installed update is incomplete.")
    previous = root / "current.json"
    if previous.exists():
        shutil.copy2(previous, root / "previous.json")
    write_json(previous, {"version": target.name})
