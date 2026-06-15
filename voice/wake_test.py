"""CLI smoke test for local wake-word detection."""

from __future__ import annotations

import argparse
import json

from voice.config import load_voice_settings
from voice.wake import WakeDebugEvent, WakeWordDetector


def _print_debug_event(event: WakeDebugEvent) -> None:
    kind = "final" if event.is_final else "partial"
    text = event.text or "<empty>"
    match = event.matched_alias or "-"
    print(
        f"[{event.elapsed_seconds:6.2f}s] {kind:<7} "
        f"rms={event.rms:.4f} peak={event.peak:.4f} "
        f"amp_peak={event.amplified_peak:.4f} match={match} text={text}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Listen until the configured wake word is detected.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Stop after this many seconds.")
    parser.add_argument("--debug", action="store_true", help="Print Vosk partial/final text and mic levels.")
    args = parser.parse_args()

    settings = load_voice_settings()
    detector = WakeWordDetector(settings)
    print("Say the configured wake word. Press Ctrl+C to stop.", flush=True)
    print(f"input_device={settings.input_device}", flush=True)
    print(f"sample_rate={settings.sample_rate}", flush=True)
    print(f"model_path={settings.wake_model_path}", flush=True)
    print(f"wake_gain={settings.wake_gain}", flush=True)
    print(f"aliases={json.dumps(settings.wake_word_aliases, ensure_ascii=True)}", flush=True)

    debug_callback = _print_debug_event if args.debug else None

    while True:
        result = detector.wait(timeout_seconds=args.timeout, debug_callback=debug_callback)

        if result is None:
            print("Wake word was not detected.", flush=True)
            return

        print("Wake word detected.", flush=True)

        if args.timeout is not None:
            return


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
