"""Cloud wake-word detection through OpenRouter STT."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
from typing import Callable

from voice.config import VoiceSettings
from voice.recorder import record_until_silence
from voice.stt import OpenRouterSTT
from voice.wake import match_wake_word


@dataclass(frozen=True)
class CloudWakeAttempt:
    """One cloud wake-word recognition attempt."""

    text: str
    speech_detected: bool
    duration_seconds: float
    matched_alias: str | None


@dataclass(frozen=True)
class CloudWakeWordResult:
    """Detected cloud wake-word details."""

    text: str
    matched_alias: str


class CloudWakeWordDetector:
    """Records short speech chunks and checks them with OpenRouter STT."""

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
        wake_record_settings = replace(
            self._settings,
            silence_seconds=self._settings.wake_silence_seconds,
            max_record_seconds=self._settings.wake_max_record_seconds,
        )

        while not stop_event.is_set():
            with tempfile.TemporaryDirectory() as tmp_dir:
                candidate_path = Path(tmp_dir) / "wake.wav"
                recording = record_until_silence(candidate_path, wake_record_settings, stop_event=stop_event)

                if stop_event.is_set():
                    return None

                if not recording.speech_detected:
                    if attempt_callback:
                        attempt_callback(
                            CloudWakeAttempt(
                                text="",
                                speech_detected=False,
                                duration_seconds=recording.duration_seconds,
                                matched_alias=None,
                            )
                        )
                    continue

                try:
                    text = await self._stt.transcribe(candidate_path)
                except Exception as exc:
                    text = f"<stt error: {exc}>"
                    match = None
                else:
                    match = match_wake_word(text, self._aliases)

                if attempt_callback:
                    attempt_callback(
                        CloudWakeAttempt(
                            text=text,
                            speech_detected=True,
                            duration_seconds=recording.duration_seconds,
                            matched_alias=match,
                        )
                    )

                if match:
                    return CloudWakeWordResult(text=text, matched_alias=match)

        return None
