"""Local wake-word detection with Vosk."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import threading
import time

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

from voice.audio_devices import require_input_device
from voice.config import VoiceSettings


@dataclass(frozen=True)
class WakeWordResult:
    """Detected wake-word details."""

    text: str
    matched_alias: str


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

        with sd.InputStream(
            samplerate=self._settings.sample_rate,
            channels=1,
            dtype="int16",
            device=device_index,
            blocksize=block_frames,
        ) as stream:
            while not stop_event.is_set():
                if timeout_seconds is not None and time.monotonic() - started_at >= timeout_seconds:
                    return None

                block, _ = stream.read(block_frames)

                if recognizer.AcceptWaveform(block.tobytes()):
                    result = _parse_result(recognizer.Result(), key="text")
                else:
                    result = _parse_result(recognizer.PartialResult(), key="partial")

                match = _match_wake_word(result, self._aliases)

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


def _match_wake_word(text: str, aliases: list[str]) -> str | None:
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
