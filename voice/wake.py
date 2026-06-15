"""Local wake-word detection with Vosk."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import threading
import time
from typing import Callable

import numpy as np
import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

from voice.audio_devices import require_input_device
from voice.config import VoiceSettings


@dataclass(frozen=True)
class WakeWordResult:
    """Detected wake-word details."""

    text: str
    matched_alias: str


@dataclass(frozen=True)
class WakeDebugEvent:
    """Diagnostic data emitted while listening for the wake word."""

    elapsed_seconds: float
    is_final: bool
    text: str
    rms: float
    peak: float
    amplified_peak: float
    matched_alias: str | None


class WakeWordDetector:
    """Listens for a small Russian wake-word grammar."""

    def __init__(self, settings: VoiceSettings) -> None:
        self._settings = settings
        model_path = settings.wake_model_path

        if not model_path.exists():
            raise RuntimeError(
                f"Wake-word model was not found: {model_path}. "
                "Run: .\\.venv\\Scripts\\python.exe -m voice.wake_setup"
            )

        SetLogLevel(-1)
        self._model = Model(str(model_path))
        self._aliases = sorted(
            {alias.strip().lower() for alias in [settings.wake_word, *settings.wake_word_aliases] if alias.strip()}
        )
        self._grammar = [*self._aliases, "[unk]"]

    def wait(
        self,
        stop_event: threading.Event | None = None,
        timeout_seconds: float | None = None,
        debug_callback: Callable[[WakeDebugEvent], None] | None = None,
    ) -> WakeWordResult | None:
        """Blocks until wake word is detected, stopped, or timed out."""
        stop_event = stop_event or threading.Event()
        device_index = require_input_device(self._settings.input_device)
        block_frames = max(1, int(self._settings.sample_rate * 0.25))
        recognizer = KaldiRecognizer(
            self._model,
            self._settings.sample_rate,
            json.dumps(self._grammar, ensure_ascii=False),
        )
        started_at = time.monotonic()

        while not stop_event.is_set():
            if timeout_seconds is not None and time.monotonic() - started_at >= timeout_seconds:
                return None

            block = sd.rec(
                block_frames,
                samplerate=self._settings.sample_rate,
                channels=1,
                dtype="float32",
                device=device_index,
            )
            sd.wait()
            block_rms = _rms_float32(block)
            block_peak = _peak_float32(block)
            amplified_block = _amplify_float32(block, self._settings.wake_gain)
            amplified_peak = _peak_float32(amplified_block)
            pcm16 = _float32_to_pcm16(amplified_block)

            if recognizer.AcceptWaveform(pcm16.tobytes()):
                is_final = True
                result = _parse_result(recognizer.Result(), key="text")
            else:
                is_final = False
                result = _parse_result(recognizer.PartialResult(), key="partial")

            match = match_wake_word(result, self._aliases)

            if debug_callback:
                debug_callback(
                    WakeDebugEvent(
                        elapsed_seconds=time.monotonic() - started_at,
                        is_final=is_final,
                        text=result,
                        rms=block_rms,
                        peak=block_peak,
                        amplified_peak=amplified_peak,
                        matched_alias=match,
                    )
                )

            if match:
                return WakeWordResult(text=result, matched_alias=match)

        return None


def _parse_result(raw_json: str, key: str) -> str:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return ""

    value = payload.get(key)
    return value.strip().lower() if isinstance(value, str) else ""


def match_wake_word(text: str, aliases: list[str]) -> str | None:
    normalized_text = _normalize_text(text)
    compact_text = normalized_text.replace(" ", "")

    for alias in aliases:
        normalized_alias = _normalize_text(alias)
        compact_alias = normalized_alias.replace(" ", "")

        if normalized_alias and normalized_alias in normalized_text:
            return alias

        if compact_alias and compact_alias in compact_text:
            return alias

    return None


def _normalize_text(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-яе\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _rms_float32(block: np.ndarray) -> float:
    audio = np.asarray(block, dtype=np.float32)

    if audio.size == 0:
        return 0.0

    return float(np.sqrt(np.mean(np.square(audio))))


def _peak_float32(block: np.ndarray) -> float:
    audio = np.asarray(block, dtype=np.float32)

    if audio.size == 0:
        return 0.0

    return float(np.max(np.abs(audio)))


def _amplify_float32(block: np.ndarray, gain: float) -> np.ndarray:
    audio = np.asarray(block, dtype=np.float32)
    return np.clip(audio * gain, -1.0, 1.0)


def _float32_to_pcm16(block: np.ndarray) -> np.ndarray:
    audio = np.asarray(block, dtype=np.float32)
    audio = np.clip(audio, -1.0, 1.0)
    return (audio * 32767.0).astype(np.int16)
