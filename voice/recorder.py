"""Microphone recording helpers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from pathlib import Path
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

from voice.audio_devices import require_input_device
from voice.config import VoiceSettings


@dataclass(frozen=True)
class RecordingResult:
    """Metadata for an automatically stopped voice recording."""

    path: Path
    speech_detected: bool
    duration_seconds: float
    silence_threshold: float


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


def record_until_silence(
    output_path: Path,
    settings: VoiceSettings,
    stop_event: threading.Event | None = None,
) -> RecordingResult:
    """Records until speech is followed by configured silence or max duration is reached."""
    device_index = require_input_device(settings.input_device)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    block_frames = max(1, int(settings.sample_rate * settings.vad_block_seconds))
    pre_roll_blocks = max(1, math.ceil(settings.pre_roll_seconds / settings.vad_block_seconds))
    max_blocks = max(1, math.ceil(settings.max_record_seconds / settings.vad_block_seconds))
    silence_limit_blocks = max(1, math.ceil(settings.silence_seconds / settings.vad_block_seconds))
    calibration_blocks = max(1, math.ceil(settings.noise_calibration_seconds / settings.vad_block_seconds))

    recorded_blocks: list[np.ndarray] = []
    pre_roll: deque[np.ndarray] = deque(maxlen=pre_roll_blocks)
    stop_event = stop_event or threading.Event()

    with sd.InputStream(
        samplerate=settings.sample_rate,
        channels=1,
        dtype="float32",
        device=device_index,
        blocksize=block_frames,
    ) as stream:
        noise_rms_values = []
        calibration_audio_blocks = []

        for _ in range(calibration_blocks):
            if stop_event.is_set():
                break

            block, _ = stream.read(block_frames)
            block = np.asarray(block, dtype=np.float32).copy()
            noise_rms_values.append(_rms(block))
            calibration_audio_blocks.append(block)

        noise_floor = float(np.median(noise_rms_values)) if noise_rms_values else 0.0
        silence_threshold = max(settings.min_speech_rms, noise_floor * settings.noise_multiplier)
        speech_detected = False
        silent_blocks = 0

        for block in calibration_audio_blocks:
            block_rms = _rms(block)
            is_speech = block_rms >= silence_threshold

            if not speech_detected:
                pre_roll.append(block)

                if is_speech:
                    speech_detected = True
                    recorded_blocks.extend(pre_roll)
                    pre_roll.clear()

                continue

            recorded_blocks.append(block)

            if is_speech:
                silent_blocks = 0
            else:
                silent_blocks += 1

        for _ in range(max_blocks):
            if stop_event.is_set():
                break

            block, _ = stream.read(block_frames)
            block = np.asarray(block, dtype=np.float32).copy()
            block_rms = _rms(block)
            is_speech = block_rms >= silence_threshold

            if not speech_detected:
                pre_roll.append(block)

                if is_speech:
                    speech_detected = True
                    recorded_blocks.extend(pre_roll)
                    pre_roll.clear()

                continue

            recorded_blocks.append(block)

            if is_speech:
                silent_blocks = 0
            else:
                silent_blocks += 1

            if silent_blocks >= silence_limit_blocks:
                break

    if not recorded_blocks:
        recorded_blocks = list(pre_roll)

    if recorded_blocks:
        audio = np.concatenate(recorded_blocks, axis=0)
    else:
        audio = np.zeros((0, 1), dtype=np.float32)

    sf.write(output_path, audio, settings.sample_rate, subtype="PCM_16")
    duration_seconds = len(audio) / settings.sample_rate if len(audio) else 0.0
    return RecordingResult(
        path=output_path,
        speech_detected=speech_detected,
        duration_seconds=duration_seconds,
        silence_threshold=silence_threshold,
    )


def _rms(block: np.ndarray) -> float:
    audio = np.asarray(block, dtype=np.float32)

    if audio.size == 0:
        return 0.0

    return float(np.sqrt(np.mean(np.square(audio))))
