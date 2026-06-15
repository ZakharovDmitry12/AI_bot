"""Voice client settings loaded from .env."""

from dataclasses import dataclass
import os

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
