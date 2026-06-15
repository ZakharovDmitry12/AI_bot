"""Microphone recording helpers."""

from __future__ import annotations

from pathlib import Path

import sounddevice as sd
import soundfile as sf

from voice.audio_devices import require_input_device
from voice.config import VoiceSettings


def record_wav(output_path: Path, settings: VoiceSettings, seconds: float | None = None) -> Path:
    """Records a mono WAV file from the configured microphone."""
    duration = seconds or settings.record_seconds
    device_index = require_input_device(settings.input_device)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    frames = int(settings.sample_rate * duration)
    audio = sd.rec(
        frames,
        samplerate=settings.sample_rate,
        channels=1,
        dtype="float32",
        device=device_index,
    )
    sd.wait()

    sf.write(output_path, audio, settings.sample_rate, subtype="PCM_16")
    return output_path
