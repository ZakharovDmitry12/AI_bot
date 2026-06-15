"""Probe input audio devices and sample rates."""

from __future__ import annotations

import argparse
import logging

import numpy as np
import sounddevice as sd

from voice.config import load_voice_settings
from voice.logging_config import configure_voice_logging


logger = logging.getLogger(__name__)
DEFAULT_SAMPLE_RATES = [8000, 16000, 44100, 48000]


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe microphone devices and sample rates.")
    parser.add_argument(
        "--rates",
        default=",".join(str(rate) for rate in DEFAULT_SAMPLE_RATES),
        help="Comma-separated sample rates to test.",
    )
    parser.add_argument("--seconds", type=float, default=0.2, help="Read duration for each OK stream.")
    args = parser.parse_args()

    settings = load_voice_settings()
    log_path = configure_voice_logging(settings.log_level)
    sample_rates = _parse_rates(args.rates)

    print(f"Logs: {log_path}")
    print("Index | Host API            | Sample | Check | Read  | RMS      | Peak     | Device")
    print("------+---------------------+--------+-------+-------+----------+----------+------------------------------")

    devices = sd.query_devices()
    hostapis = sd.query_hostapis()

    for index, device in enumerate(devices):
        input_channels = int(device.get("max_input_channels", 0))

        if input_channels <= 0:
            continue

        hostapi_index = int(device.get("hostapi", -1))
        hostapi = hostapis[hostapi_index].get("name", "?") if hostapi_index >= 0 else "?"
        device_name = str(device.get("name", ""))

        for sample_rate in sample_rates:
            check_ok, check_error = _check_device(index, sample_rate)

            if check_ok:
                read_ok, rms, peak, read_error = _read_device(index, sample_rate, args.seconds)
            else:
                read_ok, rms, peak, read_error = False, 0.0, 0.0, ""

            status_error = read_error or check_error
            print(
                f"{index:>5} | {hostapi:<19} | {sample_rate:<6} | "
                f"{_status(check_ok):<5} | {_status(read_ok):<5} | "
                f"{rms:<8.6f} | {peak:<8.6f} | {device_name}{_format_error(status_error)}"
            )


def _parse_rates(raw_rates: str) -> list[int]:
    rates = []

    for raw_rate in raw_rates.split(","):
        raw_rate = raw_rate.strip()

        if not raw_rate:
            continue

        rates.append(int(raw_rate))

    return rates or DEFAULT_SAMPLE_RATES


def _check_device(device_index: int, sample_rate: int) -> tuple[bool, str]:
    try:
        sd.check_input_settings(
            device=device_index,
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )
    except Exception as exc:
        logger.info(
            "audio_probe check failed device=%s sample_rate=%s error=%r",
            device_index,
            sample_rate,
            exc,
        )
        return False, str(exc)

    return True, ""


def _read_device(device_index: int, sample_rate: int, seconds: float) -> tuple[bool, float, float, str]:
    frames = max(1, int(sample_rate * seconds))
    block_frames = min(frames, max(1, int(sample_rate * 0.1)))
    blocks = []
    remaining_frames = frames

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=device_index,
            blocksize=block_frames,
        ) as stream:
            while remaining_frames > 0:
                frames_to_read = min(block_frames, remaining_frames)
                block, overflowed = stream.read(frames_to_read)

                if overflowed:
                    logger.warning(
                        "audio_probe overflow device=%s sample_rate=%s frames=%s",
                        device_index,
                        sample_rate,
                        frames_to_read,
                    )

                blocks.append(np.asarray(block, dtype=np.float32).copy())
                remaining_frames -= frames_to_read
    except Exception as exc:
        logger.exception(
            "audio_probe read failed device=%s sample_rate=%s",
            device_index,
            sample_rate,
        )
        return False, 0.0, 0.0, str(exc)

    audio = np.concatenate(blocks, axis=0) if blocks else np.zeros((0, 1), dtype=np.float32)
    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    return True, rms, peak, ""


def _status(ok: bool) -> str:
    return "OK" if ok else "FAIL"


def _format_error(error: str) -> str:
    if not error:
        return ""

    return f" | {error[:120]}"


if __name__ == "__main__":
    main()
