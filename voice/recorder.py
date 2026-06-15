"""Microphone recording helpers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
import math
from pathlib import Path
import threading
from typing import NoReturn

import numpy as np
import sounddevice as sd
import soundfile as sf

from voice.audio_devices import describe_device
from voice.audio_devices import require_input_device
from voice.config import VoiceSettings


logger = logging.getLogger(__name__)


class AudioInputError(RuntimeError):
    """Raised when the configured microphone cannot be opened or read."""


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
    block_frames = max(1, int(settings.sample_rate * settings.vad_block_seconds))
    _check_input_settings(device_index, settings.sample_rate)

    logger.info(
        "record_wav start path=%s duration=%.2f sample_rate=%s block_frames=%s device=%s",
        output_path,
        duration,
        settings.sample_rate,
        block_frames,
        describe_device(device_index),
    )

    try:
        with sd.InputStream(
            samplerate=settings.sample_rate,
            channels=1,
            dtype="float32",
            device=device_index,
            blocksize=block_frames,
        ) as stream:
            audio = _read_frames(stream, frames, block_frames)
    except sd.PortAudioError as exc:
        _raise_audio_input_error(exc, "record_wav", device_index, settings.sample_rate, block_frames)

    sf.write(output_path, audio, settings.sample_rate, subtype="PCM_16")
    logger.info(
        "record_wav done path=%s duration=%.2f rms=%.6f peak=%.6f",
        output_path,
        len(audio) / settings.sample_rate if len(audio) else 0.0,
        _rms(audio),
        _peak(audio),
    )
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

    noise_rms_values = []
    calibration_audio_blocks = []
    observed_rms_values = []
    observed_peak_values = []

    _check_input_settings(device_index, settings.sample_rate)

    logger.info(
        "record_until_silence start path=%s sample_rate=%s block_frames=%s "
        "silence_seconds=%.2f max_record_seconds=%.2f min_speech_rms=%.6f "
        "noise_multiplier=%.2f device=%s",
        output_path,
        settings.sample_rate,
        block_frames,
        settings.silence_seconds,
        settings.max_record_seconds,
        settings.min_speech_rms,
        settings.noise_multiplier,
        describe_device(device_index),
    )

    try:
        with sd.InputStream(
            samplerate=settings.sample_rate,
            channels=1,
            dtype="float32",
            device=device_index,
            blocksize=block_frames,
        ) as stream:
            for _ in range(calibration_blocks):
                if stop_event.is_set():
                    break

                block = _read_block(stream, block_frames)
                block_rms = _rms(block)
                noise_rms_values.append(block_rms)
                observed_rms_values.append(block_rms)
                observed_peak_values.append(_peak(block))
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

                block = _read_block(stream, block_frames)
                block_rms = _rms(block)
                observed_rms_values.append(block_rms)
                observed_peak_values.append(_peak(block))
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
    except sd.PortAudioError as exc:
        _raise_audio_input_error(exc, "record_until_silence", device_index, settings.sample_rate, block_frames)

    if not recorded_blocks:
        recorded_blocks = list(pre_roll)

    if recorded_blocks:
        audio = np.concatenate(recorded_blocks, axis=0)
    else:
        audio = np.zeros((0, 1), dtype=np.float32)

    sf.write(output_path, audio, settings.sample_rate, subtype="PCM_16")
    duration_seconds = len(audio) / settings.sample_rate if len(audio) else 0.0
    logger.info(
        "record_until_silence done path=%s speech_detected=%s duration=%.2f "
        "noise_floor=%.6f silence_threshold=%.6f max_rms=%.6f max_peak=%.6f",
        output_path,
        speech_detected,
        duration_seconds,
        noise_floor,
        silence_threshold,
        max(observed_rms_values, default=0.0),
        max(observed_peak_values, default=0.0),
    )
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


def _peak(block: np.ndarray) -> float:
    audio = np.asarray(block, dtype=np.float32)

    if audio.size == 0:
        return 0.0

    return float(np.max(np.abs(audio)))


def _read_frames(stream: sd.InputStream, frames: int, block_frames: int) -> np.ndarray:
    blocks = []
    remaining_frames = frames

    while remaining_frames > 0:
        frames_to_read = min(block_frames, remaining_frames)
        blocks.append(_read_block(stream, frames_to_read))
        remaining_frames -= frames_to_read

    if not blocks:
        return np.zeros((0, 1), dtype=np.float32)

    return np.concatenate(blocks, axis=0)


def _read_block(stream: sd.InputStream, frames: int) -> np.ndarray:
    block, overflowed = stream.read(frames)

    if overflowed:
        logger.warning("Input stream overflow while reading %s frames.", frames)

    return np.asarray(block, dtype=np.float32).copy()


def _check_input_settings(device_index: int | None, sample_rate: int) -> None:
    try:
        sd.check_input_settings(
            device=device_index,
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )
    except sd.PortAudioError as exc:
        logger.exception(
            "Input settings rejected device=%s sample_rate=%s channels=1 dtype=float32",
            describe_device(device_index),
            sample_rate,
        )
        raise AudioInputError(
            f"Input settings rejected for {describe_device(device_index)} at {sample_rate} Hz: {exc}"
        ) from exc

    logger.info(
        "Input settings OK device=%s sample_rate=%s channels=1 dtype=float32",
        describe_device(device_index),
        sample_rate,
    )


def _raise_audio_input_error(
    exc: sd.PortAudioError,
    action: str,
    device_index: int | None,
    sample_rate: int,
    block_frames: int,
) -> NoReturn:
    logger.exception(
        "Audio input failed action=%s device=%s sample_rate=%s block_frames=%s channels=1 dtype=float32",
        action,
        describe_device(device_index),
        sample_rate,
        block_frames,
    )
    raise AudioInputError(
        f"{action} failed for {describe_device(device_index)} at {sample_rate} Hz: {exc}"
    ) from exc
