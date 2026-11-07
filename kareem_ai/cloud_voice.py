"""Groq Orpheus speech generation with bounded requests and memory-only audio."""
from __future__ import annotations

import io
import re
import struct
import wave
from dataclasses import dataclass

import httpx

from .core import ProviderError, check_status
from .voice import MAX_AUDIO_BYTES, speech_text

ENGLISH_MODEL = "canopylabs/orpheus-v1-english"
ARABIC_MODEL = "canopylabs/orpheus-arabic-saudi"
CLOUD_VOICES = tuple(
    (f"Groq · {name.title()} · {language}", f"groq|{model}|{name}")
    for model, language, names in (
        (ENGLISH_MODEL, "English", ("troy", "autumn", "diana", "hannah", "austin", "daniel")),
        (ARABIC_MODEL, "Arabic Saudi", ("abdullah", "fahad", "sultan", "lulwa", "noura", "aisha")))
    for name in names)
DEFAULT_CLOUD_VOICE = CLOUD_VOICES[0][1]


def is_cloud_voice(value):
    return isinstance(value, str) and value.startswith("groq|")


def cloud_voice(value):
    if value not in {v for _, v in CLOUD_VOICES}:
        raise ProviderError("Choose one of the supported Groq cloud voices.")
    _, model, voice = value.split("|")
    return model, voice


def voice_setup_url(selection):
    from urllib.parse import urlencode
    model, _ = cloud_voice(selection)
    return "https://console.groq.com/playground?" + urlencode({"model": model})


async def speech_status(response):
    """Read bounded error metadata without exposing echoed inputs, keys, or raw bodies."""
    if response.status_code < 400:
        return
    body = bytearray()
    async for part in response.aiter_bytes():
        if len(body) + len(part) > 8192:
            break
        body.extend(part)
    code, message = "", ""
    try:
        import json
        error = json.loads(body).get("error", {})
        if isinstance(error, dict):
            code, message = str(error.get("code", "")), str(error.get("message", ""))
    except (ValueError, AttributeError, TypeError):
        pass
    if code == "model_terms_required" or "requires terms acceptance" in message.casefold():
        raise ProviderError("Groq requires you to review and accept this speech model's terms. "
                            "Open Settings → Voice → Groq voice setup, review them in your account, "
                            "then try the voice again. English and Arabic models have separate terms. "
                            "The app does not accept terms for you.")
    check_status(response, "Groq voice")


def speech_chunks(text):
    original = re.sub(r"\s+", " ", speech_text(text)).strip()
    remaining = original[:1000]
    chunks = []
    # Groq documents a 200-character limit. Never make more than five requests.
    for _ in range(5):
        if not remaining:
            break
        end = min(200, len(remaining))
        if len(remaining) > 200:
            boundary = remaining.rfind(" ", 100, 201)
            if boundary > 0:
                end = boundary
        chunks.append(remaining[:end])
        remaining = remaining[end:].lstrip()
    return chunks, bool(remaining) or len(original) > 1000


@dataclass
class CloudAudio:
    audio: bytes
    requests: int
    characters: int
    truncated: bool


def bounded_wav(clip):
    """Resolve streaming RIFF/data length markers using the bounded received bytes.

    Groq returns 0xffffffff for RIFF and data lengths. Ordinary finite lengths
    remain strict: a truncated download is never treated as streaming audio.
    """
    if len(clip) < 12 or len(clip) > MAX_AUDIO_BYTES or clip[:4] != b"RIFF" or clip[8:12] != b"WAVE":
        raise ProviderError("Groq returned invalid WAV speech audio.")
    unknown = 0xFFFFFFFF
    riff_size = struct.unpack_from("<I", clip, 4)[0]
    limit = len(clip) if riff_size == unknown else riff_size + 8
    if not 12 <= limit <= len(clip):
        raise ProviderError("Groq returned incomplete speech audio.")
    normalized = bytearray(clip[:limit])
    if riff_size == unknown:
        struct.pack_into("<I", normalized, 4, limit - 8)
    offset, frame_bytes = 12, None
    for _ in range(256):
        if offset + 8 > limit:
            break
        kind, size = struct.unpack_from("<4sI", normalized, offset)
        start = offset + 8
        if kind == b"data":
            if frame_bytes is None:
                raise ProviderError("Groq returned audio without a usable WAV format header.")
            actual_size = limit - start if size == unknown else size
            if actual_size <= 0 or start + actual_size > limit or actual_size % frame_bytes:
                raise ProviderError("Groq returned incomplete speech audio.")
            if size == unknown:
                struct.pack_into("<I", normalized, offset + 4, actual_size)
            return bytes(normalized)
        if size == unknown or start + size > limit:
            raise ProviderError("Groq returned incomplete WAV metadata.")
        if kind == b"fmt ":
            if size < 16:
                raise ProviderError("Groq returned an invalid WAV format header.")
            encoding, channels, rate, byte_rate, alignment, bits = struct.unpack_from("<HHIIHH", normalized, start)
            if (encoding != 1 or not 1 <= channels <= 2 or bits not in (8, 16, 24, 32)
                    or not 8000 <= rate <= 96000 or alignment != channels * (bits // 8)
                    or byte_rate != rate * alignment):
                raise ProviderError("Groq returned unsupported speech audio.")
            frame_bytes = alignment
        offset = start + size + (size % 2)
    raise ProviderError("Groq returned audio without a WAV data chunk.")


def combine_wav(clips):
    frames, params, size = [], None, 0
    try:
        for clip in clips:
            with wave.open(io.BytesIO(bounded_wav(clip)), "rb") as audio:
                current = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate())
                if (audio.getcomptype() != "NONE" or not 1 <= current[0] <= 2
                        or current[1] not in (1, 2, 3, 4) or not 8000 <= current[2] <= 96000
                        or audio.getnframes() / current[2] > 180):
                    raise ProviderError("Groq returned unsupported speech audio.")
                if params is not None and current != params:
                    raise ProviderError("Groq returned incompatible speech segments.")
                params = current
                pcm = audio.readframes(audio.getnframes())
                expected = audio.getnframes() * current[0] * current[1]
                if not pcm or len(pcm) != expected:
                    raise ProviderError("Groq returned incomplete speech audio.")
                size += len(pcm)
                if size > MAX_AUDIO_BYTES:
                    raise ProviderError("Generated speech exceeded the audio size limit.")
                frames.append(pcm)
        if not params:
            raise ProviderError("No speech audio was returned.")
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setnchannels(params[0])
            audio.setsampwidth(params[1])
            audio.setframerate(params[2])
            audio.writeframes(b"".join(frames))
        return output.getvalue()
    except (wave.Error, EOFError, ValueError):
        raise ProviderError("Groq returned invalid WAV speech audio.") from None


def pcm_audio(clip):
    """Decode the validated PCM WAV without loading multimedia codecs."""
    try:
        with wave.open(io.BytesIO(bounded_wav(clip)), "rb") as audio:
            rate, channels, width = audio.getframerate(), audio.getnchannels(), audio.getsampwidth()
            pcm = audio.readframes(audio.getnframes())
        if width == 3:
            import array
            pcm = array.array("i", (int.from_bytes(pcm[i:i + 3], "little", signed=True) << 8
                                    for i in range(0, len(pcm), 3))).tobytes()
            width = 4
        return pcm, rate, channels, width
    except (wave.Error, EOFError, ValueError):
        raise ProviderError("Cloud speech audio could not be decoded.") from None


async def synthesize(text, key, selection, progress=lambda _: None, transport=None):
    if not key:
        raise ProviderError("Save your Groq API key in Settings to use cloud voices.")
    model, voice = cloud_voice(selection)
    chunks, truncated = speech_chunks(text)
    if not chunks:
        raise ProviderError("There is no readable text to speak.")
    clips, total = [], 0
    async with httpx.AsyncClient(transport=transport, timeout=60, follow_redirects=False) as client:
        try:
            for number, chunk in enumerate(chunks, 1):
                progress(f"Groq cloud voice · generating segment {number}/{len(chunks)} ({len(chunk)} characters).")
                async with client.stream("POST", "https://api.groq.com/openai/v1/audio/speech",
                    headers={"Authorization": "Bearer " + key},
                    json={"model": model, "voice": voice, "input": chunk, "response_format": "wav"}) as response:
                    await speech_status(response)
                    output = bytearray()
                    async for part in response.aiter_bytes():
                        output.extend(part)
                        if total + len(output) > MAX_AUDIO_BYTES:
                            raise ProviderError("Generated speech exceeded the audio size limit.")
                    total += len(output)
                    clips.append(bytes(output))
        except httpx.HTTPError:
            raise ProviderError("Groq cloud voice connection failed. No automatic retry or Windows fallback was used.") from None
    return CloudAudio(combine_wav(clips), len(chunks), sum(map(len, chunks)), truncated)
