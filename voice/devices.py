"""CLI for listing audio devices."""

from voice.audio_devices import format_devices


def main() -> None:
    print(format_devices())


if __name__ == "__main__":
    main()
