"""Audio playback helpers."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from voice.audio_devices import describe_device
from voice.audio_devices import require_output_device
from voice.config import VoiceSettings


logger = logging.getLogger(__name__)


class AudioOutputError(RuntimeError):
    """Raised when WAV playback fails."""


def play_wav(path: Path, settings: VoiceSettings) -> None:
    """Plays a WAV file through the configured output device."""
    device_index = require_output_device(settings.output_device)
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    target_sample_rate = _default_output_sample_rate(device_index) or sample_rate

    if sample_rate != target_sample_rate:
        logger.info(
            "play_wav resample path=%s from=%s to=%s",
            path,
            sample_rate,
            target_sample_rate,
        )
        audio = _resample_audio(audio, sample_rate, target_sample_rate)
        sample_rate = target_sample_rate

    duration_seconds = len(audio) / sample_rate if len(audio) else 0.0
    logger.info(
        "play_wav start path=%s sample_rate=%s duration=%.2f device=%s",
        path,
        sample_rate,
        duration_seconds,
        describe_device(device_index),
    )

    try:
        sd.check_output_settings(
            device=device_index,
            samplerate=sample_rate,
            channels=audio.shape[1],
            dtype="float32",
        )
        sd.play(audio, sample_rate, device=device_index)
        sd.wait()
    except sd.PortAudioError as exc:
        logger.exception("play_wav failed path=%s device=%s", path, describe_device(device_index))
        raise AudioOutputError(f"Playback failed for {describe_device(device_index)}: {exc}") from exc

    logger.info("play_wav done path=%s", path)


def _default_output_sample_rate(device_index: int | None) -> int | None:
    if device_index is None:
        return None

    device = sd.query_devices(device_index)
    sample_rate = device.get("default_samplerate")

    if not sample_rate:
        return None

    return int(float(sample_rate))


def _resample_audio(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or audio.size == 0:
        return audio

    source_frames = audio.shape[0]
    target_frames = max(1, int(round(source_frames * target_rate / source_rate)))
    source_positions = np.linspace(0.0, source_frames - 1, num=source_frames)
    target_positions = np.linspace(0.0, source_frames - 1, num=target_frames)
    channels = [
        np.interp(target_positions, source_positions, audio[:, channel])
        for channel in range(audio.shape[1])
    ]
    return np.stack(channels, axis=1).astype(np.float32)
