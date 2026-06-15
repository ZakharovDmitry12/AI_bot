"""Download and install the small Russian Vosk wake-word model."""

from __future__ import annotations

from pathlib import Path
import urllib.request
from zipfile import ZipFile

from voice.config import load_voice_settings


MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"


def main() -> None:
    settings = load_voice_settings()
    model_path = settings.wake_model_path

    if model_path.exists():
        print(f"Wake-word model already exists: {model_path}")
        return

    install_root = model_path.parent
    install_root.mkdir(parents=True, exist_ok=True)
    archive_path = install_root / "vosk-model-small-ru-0.22.zip"

    if not archive_path.exists():
        print(f"Downloading {MODEL_URL}")
        urllib.request.urlretrieve(MODEL_URL, archive_path)

    print(f"Extracting {archive_path}")

    with ZipFile(archive_path) as archive:
        archive.extractall(install_root)

    if not model_path.exists():
        raise RuntimeError(f"Expected model path was not created: {model_path}")

    print(f"Wake-word model installed: {model_path}")


if __name__ == "__main__":
    main()
