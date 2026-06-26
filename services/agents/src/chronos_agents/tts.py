"""Offline text-to-speech via Piper (CPU, no network) — narration for the news-anchor videos.

Piper renders a short script to a WAV in well under real-time on CPU. The voice model (.onnx +
.onnx.json) ships in the agents image; its path comes from config. Best-effort: any failure
returns ``None`` so the caller falls back to a silent (caption-only) video.
"""

from __future__ import annotations

import io
import logging
import wave

log = logging.getLogger("chronos.agents.tts")

# Loading a voice parses a ~60 MB ONNX graph — cache per model path across calls.
_VOICES: dict[str, object] = {}


def _load(model_path: str):
    voice = _VOICES.get(model_path)
    if voice is None:
        from piper import PiperVoice  # lazy: keep the heavy import out of module load
        voice = PiperVoice.load(model_path)
        _VOICES[model_path] = voice
    return voice


def synthesize(text: str, *, model_path: str) -> bytes | None:
    """Render ``text`` to WAV bytes via the Piper voice at ``model_path`` (or ``None``)."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        voice = _load(model_path)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            voice.synthesize_wav(text, wf)
        return buf.getvalue()
    except Exception:  # noqa: BLE001 - narration is optional; never crash the render
        log.warning("tts: synthesis failed", exc_info=True)
        return None
