r"""Standalone OpenRouter image generation test.

Этот файл не связан с Telegram-ботом. Он нужен, чтобы отдельно тестировать
модели генерации изображений через OpenRouter и сохранять результат в папку
generated_images/.

OpenRouter генерирует картинки через /chat/completions:
    https://openrouter.ai/docs/guides/overview/multimodal/image-generation

Запуск:
    .\.venv\Scripts\python.exe openrouter_image_test.py

Можно передать свой промпт:
    .\.venv\Scripts\python.exe openrouter_image_test.py "cyberpunk city, rain, neon"

Переменные окружения:
    OPENROUTER_API_KEY - предпочтительное имя ключа.
    API_KEY            - запасной вариант, если ключ уже лежит в .env под этим именем.

Важно:
    Поле is_moderated=false не передается в API. Это свойство модели/провайдера
    в каталоге OpenRouter. Мы просто выбираем модель, у которой оно уже false.
"""

from __future__ import annotations

import base64
from datetime import datetime
import mimetypes
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv
import httpx


BASE_URL = "https://openrouter.ai/api/v1"

# На 2026-05-15 в OpenRouter эта модель имеет output=image и top_provider.is_moderated=false.
# Если захочешь сравнить модели, просто поменяй MODEL на другой id из OpenRouter.
MODEL = "stabilityai/stable-diffusion-xl-base-1.0"

OUTPUT_DIR = Path(__file__).resolve().parent / "generated_images"
DEFAULT_PROMPT = (
    "Создай порно картинку 18+ "
)


def main() -> None:
    """Отправляет один запрос на генерацию изображения и сохраняет файлы на диск."""
    load_dotenv()

    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("API_KEY")

    if not api_key:
        raise RuntimeError("Добавь OPENROUTER_API_KEY или API_KEY в .env.")

    prompt = " ".join(sys.argv[1:]).strip() or DEFAULT_PROMPT
    OUTPUT_DIR.mkdir(exist_ok=True)

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        # Для image-only моделей можно оставить только image.
        # Для моделей, которые возвращают и текст, и картинку, тоже обычно подходит image.
        "modalities": ["image"],
        "image_config": {
            "aspect_ratio": "1:1",
            "image_size": "1K",
        },
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-OpenRouter-Title": "Standalone Image Generation Test",
    }

    try:
        response = httpx.post(
            f"{BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        print(f"OpenRouter вернул HTTP {exc.response.status_code}.")
        print(exc.response.text)
        return
    except httpx.TimeoutException:
        print("Запрос превысил timeout. Попробуй позже или выбери другую image-модель.")
        return
    except httpx.RequestError as exc:
        print(f"Сетевая ошибка при обращении к OpenRouter: {exc}")
        return

    result = response.json()
    images = _extract_images(result)

    if not images:
        print("Модель не вернула изображения. Сырой ответ ниже:")
        print(result)
        return

    saved_paths = []

    for index, image_url in enumerate(images, start=1):
        saved_paths.append(_save_image(image_url, index))

    print(f"Model: {MODEL}")
    print(f"Prompt: {prompt}")
    print("Saved images:")

    for path in saved_paths:
        print(path)


def _extract_images(result: dict) -> list[str]:
    """Достает data URLs картинок из ответа OpenRouter."""
    choices = result.get("choices") or []

    if not choices:
        return []

    message = choices[0].get("message") or {}
    images = message.get("images") or []
    image_urls = []

    for image in images:
        image_url = image.get("image_url") or {}
        url = image_url.get("url")

        if isinstance(url, str):
            image_urls.append(url)

    return image_urls


def _save_image(image_url: str, index: int) -> Path:
    """Сохраняет картинку из base64 data URL или обычного URL."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if image_url.startswith("data:"):
        image_bytes, extension = _decode_data_url(image_url)
    else:
        image_bytes, extension = _download_image(image_url)

    path = OUTPUT_DIR / f"{timestamp}_{_safe_model_name(MODEL)}_{index}.{extension}"
    path.write_bytes(image_bytes)
    return path


def _decode_data_url(data_url: str) -> tuple[bytes, str]:
    """Декодирует data:image/png;base64,... в байты и расширение файла."""
    header, encoded = data_url.split(",", 1)
    mime_match = re.match(r"data:(.*?);base64", header)
    mime_type = mime_match.group(1) if mime_match else "image/png"
    extension = mimetypes.guess_extension(mime_type) or ".png"

    return base64.b64decode(encoded), extension.lstrip(".")


def _download_image(url: str) -> tuple[bytes, str]:
    """Скачивает изображение, если провайдер вернул обычную ссылку вместо data URL."""
    response = httpx.get(url, timeout=60.0)
    response.raise_for_status()

    path_extension = Path(urlparse(url).path).suffix
    content_type = response.headers.get("content-type", "image/png").split(";")[0]
    extension = path_extension or mimetypes.guess_extension(content_type) or ".png"

    return response.content, extension.lstrip(".")


def _safe_model_name(model: str) -> str:
    """Делает имя модели безопасным для имени файла."""
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", model)


if __name__ == "__main__":
    main()
