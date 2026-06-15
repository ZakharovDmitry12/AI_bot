"""Voice client settings loaded from .env."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class VoiceSettings:
    """Settings for recording, transcription, synthesis, and playback."""

    input_device: str | None
    output_device: str | None
    user_id: str
    record_seconds: float
    sample_rate: int
    stt_model: str
    stt_fallback_model: str | None
    stt_language: str | None
    piper_exe: str | None
    piper_model: str | None
    piper_config: str | None
    wake_word: str
    wake_word_aliases: list[str]
    wake_model_path: Path
    wake_gain: float
    wake_silence_seconds: float
    wake_max_record_seconds: float
    silence_seconds: float
    max_record_seconds: float
    pre_roll_seconds: float
    min_speech_rms: float
    noise_multiplier: float
    vad_block_seconds: float
    noise_calibration_seconds: float
    log_level: str


def load_voice_settings() -> VoiceSettings:
    """Loads voice-only settings without requiring Telegram credentials."""
    load_dotenv()

    return VoiceSettings(
        input_device=_get_optional_env("VOICE_INPUT_DEVICE", default="SoundJoy2"),
        output_device=_get_optional_env("VOICE_OUTPUT_DEVICE", default="SoundJoy2"),
        user_id=os.getenv("VOICE_USER_ID", "local-speaker"),
        record_seconds=_get_float_env("VOICE_RECORD_SECONDS", 8.0),
        sample_rate=_get_int_env("VOICE_SAMPLE_RATE", 16000),
        stt_model=os.getenv("OPENROUTER_STT_MODEL", "openai/gpt-4o-transcribe"),
        stt_fallback_model=_get_optional_env(
            "OPENROUTER_STT_FALLBACK_MODEL",
            default="openai/whisper-large-v3",
        ),
        stt_language=_get_optional_env("OPENROUTER_STT_LANGUAGE", default="ru"),
        piper_exe=_get_optional_env("PIPER_EXE", default="piper"),
        piper_model=_get_optional_env("PIPER_MODEL"),
        piper_config=_get_optional_env("PIPER_CONFIG"),
        wake_word=os.getenv("VOICE_WAKE_WORD", "джарвис").strip().lower(),
        wake_word_aliases=_get_csv_env(
            "VOICE_WAKE_WORD_ALIASES",
            default=[
                "джарвис",
                "джарвиз",
                "джервис",
                "джар вис",
                "джар виз",
                "жарвис",
                "жарвиз",
                "ярвис",
            ],
        ),
        wake_model_path=Path(
            os.getenv(
                "VOICE_WAKE_MODEL_PATH",
                r".venv\vosk\vosk-model-small-ru-0.22",
            )
        ),
        wake_gain=_get_float_env("VOICE_WAKE_GAIN", 12.0),
        wake_silence_seconds=_get_float_env("VOICE_WAKE_SILENCE_SECONDS", 0.8),
        wake_max_record_seconds=_get_float_env("VOICE_WAKE_MAX_RECORD_SECONDS", 4.0),
        silence_seconds=_get_float_env("VOICE_SILENCE_SECONDS", 2.0),
        max_record_seconds=_get_float_env("VOICE_MAX_RECORD_SECONDS", 20.0),
        pre_roll_seconds=_get_float_env("VOICE_PRE_ROLL_SECONDS", 0.3),
        min_speech_rms=_get_float_env("VOICE_MIN_SPEECH_RMS", 0.003),
        noise_multiplier=_get_float_env("VOICE_NOISE_MULTIPLIER", 3.0),
        vad_block_seconds=_get_float_env("VOICE_VAD_BLOCK_SECONDS", 0.1),
        noise_calibration_seconds=_get_float_env("VOICE_NOISE_CALIBRATION_SECONDS", 0.4),
        log_level=os.getenv("VOICE_LOG_LEVEL", "INFO").strip().upper() or "INFO",
    )


def _get_optional_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)

    if value is None:
        return default

    value = value.strip()
    return value or None


def _get_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)

    if not raw_value:
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc

    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")

    return value


def _get_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)

    if not raw_value:
        return default

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number.") from exc

    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")

    return value


def _get_csv_env(name: str, default: list[str]) -> list[str]:
    raw_value = os.getenv(name)

    if not raw_value:
        return default

    values = [value.strip().lower() for value in raw_value.split(",") if value.strip()]
    return values or default
