"""Helpers for finding and displaying sounddevice audio devices."""

from __future__ import annotations

import re

import sounddevice as sd


class AudioDeviceNotFound(RuntimeError):
    """Raised when a configured input or output device is unavailable."""


def require_input_device(name: str | None) -> int | None:
    """Returns input device index or None for the system default device."""
    return _find_device(name=name, direction="input")


def require_output_device(name: str | None) -> int | None:
    """Returns output device index or None for the system default device."""
    return _find_device(name=name, direction="output")


def describe_device(index: int | None) -> str:
    """Returns a compact human-readable device description."""
    if index is None:
        return "system default"

    devices = sd.query_devices()

    if index < 0 or index >= len(devices):
        return f"#{index} <missing>"

    device = devices[index]
    hostapis = sd.query_hostapis()
    hostapi_index = int(device.get("hostapi", -1))
    hostapi = hostapis[hostapi_index].get("name", "?") if hostapi_index >= 0 else "?"
    return f"#{index} [{hostapi}] {device.get('name')}"


def format_devices() -> str:
    """Returns a readable table of currently available audio devices."""
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    lines = [
        "Index | Host API            | I/O    | Channels | Default SR | Name",
        "------+---------------------+--------+----------+------------+----------------------------------------",
    ]

    for index, device in enumerate(devices):
        hostapi_index = int(device.get("hostapi", -1))
        hostapi = hostapis[hostapi_index].get("name", "?") if hostapi_index >= 0 else "?"
        input_channels = int(device.get("max_input_channels", 0))
        output_channels = int(device.get("max_output_channels", 0))
        default_samplerate = int(float(device.get("default_samplerate", 0) or 0))
        kinds = []

        if input_channels:
            kinds.append("input")

        if output_channels:
            kinds.append("output")

        kind = ",".join(kinds) or "-"
        channels = f"{input_channels}/{output_channels}"
        lines.append(
            f"{index:>5} | {hostapi:<19} | {kind:<6} | {channels:<8} | "
            f"{default_samplerate:<10} | {device.get('name')}"
        )

    return "\n".join(lines)


def _find_device(name: str | None, direction: str) -> int | None:
    if not name:
        return None

    if name.isdigit():
        return _validate_device_index(int(name), direction)

    normalized_names = _device_name_candidates(name)
    channel_key = "max_input_channels" if direction == "input" else "max_output_channels"
    matches = []

    for index, device in enumerate(sd.query_devices()):
        device_name = str(device.get("name", ""))
        normalized_device_name = _normalize_device_name(device_name)
        channels = int(device.get(channel_key, 0))

        if channels > 0 and any(candidate in normalized_device_name for candidate in normalized_names):
            matches.append((index, device))

    if matches:
        matches.sort(key=lambda item: _device_preference_score(item[1]))
        return matches[0][0]

    raise AudioDeviceNotFound(
        f"Audio {direction} device containing '{name}' was not found.\n\n{format_devices()}"
    )


def _validate_device_index(index: int, direction: str) -> int:
    devices = sd.query_devices()

    if index < 0 or index >= len(devices):
        raise AudioDeviceNotFound(f"Audio {direction} device index {index} was not found.\n\n{format_devices()}")

    channel_key = "max_input_channels" if direction == "input" else "max_output_channels"
    channels = int(devices[index].get(channel_key, 0))

    if channels <= 0:
        raise AudioDeviceNotFound(
            f"Audio device index {index} is not a valid {direction} device.\n\n{format_devices()}"
        )

    return index


def _device_preference_score(device: dict) -> int:
    hostapis = sd.query_hostapis()
    hostapi_index = int(device.get("hostapi", -1))
    hostapi_name = hostapis[hostapi_index].get("name", "").lower() if hostapi_index >= 0 else ""

    if "wasapi" in hostapi_name:
        return 0

    if "directsound" in hostapi_name:
        return 1

    if "mme" in hostapi_name:
        return 2

    if "wdm-ks" in hostapi_name:
        return 9

    return 5


def _device_name_candidates(name: str) -> set[str]:
    normalized_name = _normalize_device_name(name)
    without_trailing_digits = re.sub(r"\d+$", "", normalized_name)
    return {candidate for candidate in {normalized_name, without_trailing_digits} if candidate}


def _normalize_device_name(name: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", "", name.lower())
