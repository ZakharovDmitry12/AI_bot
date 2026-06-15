"""OpenRouter Speech-to-Text client."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import aiohttp

from bot.config import Settings
from voice.config import VoiceSettings


class OpenRouterSTT:
    """Transcribes local audio files through OpenRouter STT API."""

    def __init__(self, app_settings: Settings, voice_settings: VoiceSettings) -> None:
        self._app_settings = app_settings
        self._voice_settings = voice_settings

    async def transcribe(self, audio_path: Path) -> str:
        """Returns transcribed text, trying the fallback model once if needed."""
        model_ids = [self._voice_settings.stt_model]

        if (
            self._voice_settings.stt_fallback_model
            and self._voice_settings.stt_fallback_model not in model_ids
        ):
            model_ids.append(self._voice_settings.stt_fallback_model)

        errors = []

        for model_id in model_ids:
            try:
                return await self._transcribe_with_model(audio_path, model_id)
            except Exception as exc:
                errors.append(f"{model_id}: {exc}")

        raise RuntimeError("OpenRouter STT failed. " + " | ".join(errors))

    async def _transcribe_with_model(self, audio_path: Path, model_id: str) -> str:
        audio_data = base64.b64encode(audio_path.read_bytes()).decode("ascii")
        audio_format = audio_path.suffix.lower().lstrip(".") or "wav"
        payload = {
            "model": model_id,
            "input_audio": {
                "data": audio_data,
                "format": audio_format,
            },
            "temperature": 0,
        }

        if self._voice_settings.stt_language:
            payload["language"] = self._voice_settings.stt_language

        headers = {
            "Authorization": f"Bearer {self._app_settings.llm_api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": self._app_settings.openrouter_app_name,
        }

        if self._app_settings.openrouter_site_url:
            headers["HTTP-Referer"] = self._app_settings.openrouter_site_url

        endpoint = f"{self._app_settings.llm_base_url.rstrip('/')}/audio/transcriptions"

        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, json=payload, timeout=120) as response:
                response_text = await response.text()

                if response.status >= 400:
                    raise RuntimeError(f"HTTP {response.status}: {response_text}")

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON response: {response_text}") from exc

        text = result.get("text")

        if not isinstance(text, str):
            raise RuntimeError(f"Response does not contain text: {result}")

        return text.strip()
