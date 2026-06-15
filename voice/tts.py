"""Piper text-to-speech wrapper and CLI smoke test."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from voice.config import VoiceSettings, load_voice_settings
from voice.player import play_wav


class PiperTTS:
    """Synthesizes speech with a local Piper executable."""

    def __init__(self, settings: VoiceSettings) -> None:
        self._settings = settings

    def synthesize_to_file(self, text: str, output_path: Path) -> Path:
        """Writes synthesized speech to a WAV file."""
        piper_exe = self._resolve_piper_exe()
        model_path = self._require_path(self._settings.piper_model, "PIPER_MODEL")
        speech_text = markdown_to_speech_text(text)

        if self._settings.piper_config:
            self._require_path(self._settings.piper_config, "PIPER_CONFIG")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        for output_flag in ("--output_file", "--output-file"):
            if output_path.exists():
                output_path.unlink()

            result = subprocess.run(
                [piper_exe, "--model", str(model_path), output_flag, str(output_path)],
                input=speech_text,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )

            if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                return output_path

            last_error = (result.stderr or result.stdout or "").strip()

        raise RuntimeError(f"Piper failed to synthesize speech: {last_error}")

    def _resolve_piper_exe(self) -> str:
        configured = self._settings.piper_exe or "piper"
        configured_path = Path(configured)

        if configured_path.exists():
            return str(configured_path)

        found = shutil.which(configured)

        if found:
            return found

        raise RuntimeError("PIPER_EXE is not set and 'piper' was not found in PATH.")

    @staticmethod
    def _require_path(value: str | None, env_name: str) -> Path:
        if not value:
            raise RuntimeError(f"{env_name} is not set.")

        path = Path(value)

        if not path.exists():
            raise RuntimeError(f"{env_name} does not exist: {path}")

        return path


def markdown_to_speech_text(text: str) -> str:
    """Converts common Markdown formatting into text that TTS should read naturally."""
    speech = text
    speech = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", speech)
    speech = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", speech)
    speech = re.sub(r"```[a-zA-Z0-9_-]*\s*([\s\S]*?)```", r"\1", speech)
    speech = re.sub(r"`([^`]*)`", r"\1", speech)
    speech = re.sub(r"^#{1,6}\s*", "", speech, flags=re.MULTILINE)
    speech = re.sub(r"^\s*>\s?", "", speech, flags=re.MULTILINE)
    speech = re.sub(r"^\s*[-*+]\s+", "", speech, flags=re.MULTILINE)
    speech = re.sub(r"^\s*\d+[.)]\s+", "", speech, flags=re.MULTILINE)
    speech = re.sub(r"[*_~]{1,3}([^*_~]+)[*_~]{1,3}", r"\1", speech)
    speech = re.sub(r"[*_~#>|]+", "", speech)
    speech = re.sub(r"\s+", " ", speech)
    return speech.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthesize text with Piper and play it.")
    parser.add_argument("text", nargs="*", help="Text to synthesize.")
    args = parser.parse_args()

    text = " ".join(args.text).strip()

    if not text:
        text = input("Text: ").strip()

    if not text:
        print("No text provided.")
        sys.exit(1)

    settings = load_voice_settings()

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "tts.wav"
        PiperTTS(settings).synthesize_to_file(text, output_path)
        play_wav(output_path, settings)


if __name__ == "__main__":
    main()
