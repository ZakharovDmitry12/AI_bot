"""CLI smoke test for local wake-word detection."""

from __future__ import annotations

import argparse

from voice.config import load_voice_settings
from voice.wake import WakeWordDetector


def main() -> None:
    parser = argparse.ArgumentParser(description="Listen until the configured wake word is detected.")
    parser.add_argument("--timeout", type=float, default=None, help="Stop after this many seconds.")
    args = parser.parse_args()

    settings = load_voice_settings()
    detector = WakeWordDetector(settings)
    print("Say the configured wake word. Press Ctrl+C to stop.")

    while True:
        result = detector.wait(timeout_seconds=args.timeout)

        if result is None:
            print("Wake word was not detected.")
            return

        print("Wake word detected.")

        if args.timeout is not None:
            return


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
