from __future__ import annotations

import io
import re
import wave

import httpx

from .core import ProviderError, check_status

MAX_AUDIO_BYTES = 12 * 1024 * 1024


def wav_audio(pcm: bytes, sample_rate: int, channels: int) -> bytes:
    if not pcm or len(pcm) > MAX_AUDIO_BYTES or sample_rate <= 0 or not 1 <= channels <= 8:
        raise ValueError("No usable recording, or audio exceeded the recording limit.")
    frame_size = channels * 2
    pcm = pcm[:len(pcm) // frame_size * frame_size]
    if not pcm:
        raise ValueError("The recording is too short.")
    target = io.BytesIO()
    with wave.open(target, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm)
    return target.getvalue()


async def transcribe(audio: bytes, key: str, model="whisper-large-v3-turbo", transport=None):
    if not key:
        raise ProviderError("Add your Groq API key in Settings to use voice input.")
    if not audio or len(audio) > MAX_AUDIO_BYTES + 44:
        raise ProviderError("The recording is empty or too large.")
    if model not in ("whisper-large-v3-turbo", "whisper-large-v3"):
        raise ProviderError("Choose a supported Whisper transcription model in Settings.")
    async with httpx.AsyncClient(transport=transport, timeout=60, follow_redirects=False) as client:
        try:
            response = await client.post("https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": "Bearer " + key},
                data={"model": model, "response_format": "json"},
                files={"file": ("recording.wav", audio, "audio/wav")})
            check_status(response, "Groq voice")
            text = response.json().get("text", "")
            if not isinstance(text, str) or not text.strip():
                raise ProviderError("Groq returned no speech text. Try a clearer recording.")
            return text.strip()[:16000]
        except (httpx.HTTPError, ValueError, TypeError):
            raise ProviderError("Groq voice: connection or response error. No automatic retry sent.") from None


def speech_text(markdown):
    # Never read generated code/actions aloud. Keep spoken replies reasonably short.
    text = re.sub(r"```.*?```", "", markdown, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[\*_`#>|]", "", text)
    return text.strip()[:6000]
