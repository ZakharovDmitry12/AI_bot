"""Audio playback helpers."""

from __future__ import annotations

from pathlib import Path

import sounddevice as sd
import soundfile as sf

from voice.audio_devices import require_output_device
from voice.config import VoiceSettings


def play_wav(path: Path, settings: VoiceSettings) -> None:
    """Plays a WAV file through the configured output device."""
    device_index = require_output_device(settings.output_device)
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    sd.play(audio, sample_rate, device=device_index)
    sd.wait()
