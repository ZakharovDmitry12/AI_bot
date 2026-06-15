"""Cloud wake-word detection through continuous OpenRouter STT checks."""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
import logging
import math
from pathlib import Path
import tempfile
import threading
import time
from typing import Callable

import numpy as np
import sounddevice as sd
import soundfile as sf

from voice.audio_devices import describe_device
from voice.audio_devices import require_input_device
from voice.config import VoiceSettings
from voice.recorder import AudioInputError
from voice.recorder import calculate_silence_threshold
from voice.stt import OpenRouterSTT
from voice.wake import match_wake_word


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CloudWakeAttempt:
    """One cloud wake-word recognition attempt."""

    text: str
    speech_detected: bool
    duration_seconds: float
    matched_alias: str | None
    max_rms: float = 0.0
    max_peak: float = 0.0
    silence_threshold: float = 0.0
    voiced_seconds: float = 0.0


@dataclass(frozen=True)
class CloudWakeWordResult:
    """Detected cloud wake-word details."""

    text: str
    matched_alias: str


@dataclass(frozen=True)
class _WakeAudioBlock:
    audio: np.ndarray
    rms: float
    peak: float
    is_speech: bool


class CloudWakeWordDetector:
    """Continuously records audio and checks voiced chunks with OpenRouter STT."""

    def __init__(self, settings: VoiceSettings, stt: OpenRouterSTT) -> None:
        self._settings = settings
        self._stt = stt
        self._aliases = [settings.wake_word, *settings.wake_word_aliases]

    async def wait(
        self,
        stop_event: threading.Event,
        attempt_callback: Callable[[CloudWakeAttempt], None] | None = None,
    ) -> CloudWakeWordResult | None:
        """Blocks until the wake word is transcribed or the stop event is set."""
        device_index = require_input_device(self._settings.input_device)
        sample_rate = self._settings.sample_rate
        block_frames = max(1, int(sample_rate * self._settings.vad_block_seconds))
        window_blocks = max(1, int(self._settings.wake_window_seconds / self._settings.vad_block_seconds))
        interval_seconds = self._settings.wake_stt_interval_seconds
        min_voiced_seconds = self._settings.wake_min_voiced_seconds
        warmup_blocks = max(0, math.ceil(self._settings.audio_warmup_seconds / self._settings.vad_block_seconds))
        calibration_blocks = max(
            1,
            math.ceil(self._settings.noise_calibration_seconds / self._settings.vad_block_seconds),
        )
        recent_blocks: deque[_WakeAudioBlock] = deque(maxlen=window_blocks)
        pending_attempt: asyncio.Task[CloudWakeAttempt] | None = None
        last_attempt_at = 0.0

        _check_input_settings(device_index, sample_rate)
        logger.info(
            "cloud_wake start device=%s sample_rate=%s block_frames=%s interval=%.2f "
            "window=%.2f min_voiced=%.2f warmup=%.2f min_rms=%.6f max_threshold=%.6f",
            describe_device(device_index),
            sample_rate,
            block_frames,
            interval_seconds,
            self._settings.wake_window_seconds,
            min_voiced_seconds,
            self._settings.audio_warmup_seconds,
            self._settings.min_speech_rms,
            self._settings.max_silence_threshold,
        )

        try:
            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                device=device_index,
                blocksize=block_frames,
            ) as stream:
                calibration_audio = []

                for _ in range(warmup_blocks):
                    if stop_event.is_set():
                        return None

                    _read_block(stream, block_frames)

                for _ in range(calibration_blocks):
                    if stop_event.is_set():
                        return None

                    calibration_audio.append(_read_block(stream, block_frames))

                noise_values = [_rms(block) for block in calibration_audio]
                noise_floor, silence_threshold = calculate_silence_threshold(noise_values, self._settings)
                logger.info(
                    "cloud_wake calibrated noise_floor=%.6f silence_threshold=%.6f calibration_rms=%s",
                    noise_floor,
                    silence_threshold,
                    ",".join(f"{value:.6f}" for value in noise_values),
                )

                for block in calibration_audio:
                    recent_blocks.append(_to_wake_block(block, silence_threshold))

                while not stop_event.is_set():
                    if pending_attempt and pending_attempt.done():
                        result = await _consume_attempt(pending_attempt, attempt_callback)
                        pending_attempt = None

                        if result:
                            return result

                    block = _read_block(stream, block_frames)
                    recent_blocks.append(_to_wake_block(block, silence_threshold))
                    now = time.monotonic()

                    if now - last_attempt_at >= interval_seconds:
                        last_attempt_at = now

                        if pending_attempt and not pending_attempt.done():
                            logger.debug("cloud_wake skip STT attempt because previous attempt is still running")
                        else:
                            attempt_audio = _extract_speech_window(
                                list(recent_blocks),
                                sample_rate,
                                min_voiced_seconds,
                            )

                            if attempt_audio is None:
                                stats = _window_stats(list(recent_blocks), sample_rate)
                                logger.info(
                                    "cloud_wake no speech window duration=%.2f voiced=%.2f max_rms=%.6f max_peak=%.6f threshold=%.6f",
                                    stats[0],
                                    stats[3],
                                    stats[1],
                                    stats[2],
                                    silence_threshold,
                                )
                                if attempt_callback:
                                    attempt_callback(
                                        CloudWakeAttempt(
                                            text="",
                                            speech_detected=False,
                                            duration_seconds=stats[0],
                                            matched_alias=None,
                                            max_rms=stats[1],
                                            max_peak=stats[2],
                                            silence_threshold=silence_threshold,
                                            voiced_seconds=stats[3],
                                        )
                                    )
                            else:
                                pending_attempt = asyncio.create_task(
                                    self._transcribe_attempt(attempt_audio, silence_threshold),
                                    name="cloud-wake-stt-attempt",
                                )

                    await asyncio.sleep(0)
        except sd.PortAudioError as exc:
            logger.exception(
                "cloud_wake audio input failed device=%s sample_rate=%s block_frames=%s",
                describe_device(device_index),
                sample_rate,
                block_frames,
            )
            raise AudioInputError(
                f"cloud_wake failed for {describe_device(device_index)} at {sample_rate} Hz: {exc}"
            ) from exc
        finally:
            if pending_attempt and not pending_attempt.done():
                pending_attempt.cancel()

                with suppress(asyncio.CancelledError):
                    await pending_attempt

        return None

    async def _transcribe_attempt(self, audio: np.ndarray, silence_threshold: float) -> CloudWakeAttempt:
        duration_seconds = len(audio) / self._settings.sample_rate if len(audio) else 0.0
        rms = _rms(audio)
        peak = _peak(audio)

        with tempfile.TemporaryDirectory() as tmp_dir:
            candidate_path = Path(tmp_dir) / "wake.wav"
            sf.write(candidate_path, audio, self._settings.sample_rate, subtype="PCM_16")
            logger.info(
                "cloud_wake STT attempt duration=%.2f rms=%.6f peak=%.6f path=%s",
                duration_seconds,
                rms,
                peak,
                candidate_path,
            )

            try:
                text = await self._stt.transcribe(candidate_path)
            except Exception as exc:
                logger.exception("cloud_wake STT attempt failed")
                text = f"<stt error: {exc}>"
                match = None
            else:
                match = match_wake_word(text, self._aliases)
                logger.info("cloud_wake STT text=%r match=%r", text, match)

        return CloudWakeAttempt(
            text=text,
            speech_detected=True,
            duration_seconds=duration_seconds,
            matched_alias=match,
            max_rms=rms,
            max_peak=peak,
            silence_threshold=silence_threshold,
            voiced_seconds=duration_seconds,
        )


async def _consume_attempt(
    task: asyncio.Task[CloudWakeAttempt],
    attempt_callback: Callable[[CloudWakeAttempt], None] | None,
) -> CloudWakeWordResult | None:
    attempt = task.result()

    if attempt_callback:
        attempt_callback(attempt)

    if attempt.matched_alias:
        return CloudWakeWordResult(text=attempt.text, matched_alias=attempt.matched_alias)

    return None


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
            "cloud_wake input settings rejected device=%s sample_rate=%s",
            describe_device(device_index),
            sample_rate,
        )
        raise AudioInputError(
            f"Input settings rejected for {describe_device(device_index)} at {sample_rate} Hz: {exc}"
        ) from exc


def _read_block(stream: sd.InputStream, frames: int) -> np.ndarray:
    block, overflowed = stream.read(frames)

    if overflowed:
        logger.warning("cloud_wake input stream overflow while reading %s frames", frames)

    return np.asarray(block, dtype=np.float32).copy()


def _to_wake_block(block: np.ndarray, silence_threshold: float) -> _WakeAudioBlock:
    rms = _rms(block)
    return _WakeAudioBlock(
        audio=block,
        rms=rms,
        peak=_peak(block),
        is_speech=rms >= silence_threshold,
    )


def _extract_speech_window(
    blocks: list[_WakeAudioBlock],
    sample_rate: int,
    min_voiced_seconds: float,
) -> np.ndarray | None:
    speech_indices = [index for index, block in enumerate(blocks) if block.is_speech]

    if not speech_indices:
        return None

    voiced_frames = sum(len(blocks[index].audio) for index in speech_indices)
    voiced_seconds = voiced_frames / sample_rate

    if voiced_seconds < min_voiced_seconds:
        logger.debug("cloud_wake skip short voiced window duration=%.2f", voiced_seconds)
        return None

    start_index = speech_indices[0]
    end_index = speech_indices[-1] + 1
    audio_blocks = [block.audio for block in blocks[start_index:end_index]]

    if not audio_blocks:
        return None

    audio = np.concatenate(audio_blocks, axis=0)
    logger.debug(
        "cloud_wake speech window duration=%.2f voiced=%.2f max_rms=%.6f max_peak=%.6f",
        len(audio) / sample_rate,
        voiced_seconds,
        max((block.rms for block in blocks[start_index:end_index]), default=0.0),
        max((block.peak for block in blocks[start_index:end_index]), default=0.0),
    )
    return audio


def _window_stats(blocks: list[_WakeAudioBlock], sample_rate: int) -> tuple[float, float, float, float]:
    if not blocks:
        return 0.0, 0.0, 0.0, 0.0

    frames = sum(len(block.audio) for block in blocks)
    voiced_frames = sum(len(block.audio) for block in blocks if block.is_speech)
    return (
        frames / sample_rate,
        max((block.rms for block in blocks), default=0.0),
        max((block.peak for block in blocks), default=0.0),
        voiced_frames / sample_rate,
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
