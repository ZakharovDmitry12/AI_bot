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


def format_devices() -> str:
    """Returns a readable table of currently available audio devices."""
    devices = sd.query_devices()
    lines = [
        "Index | I/O    | Channels | Name",
        "------+--------+----------+----------------------------------------",
    ]

    for index, device in enumerate(devices):
        input_channels = int(device.get("max_input_channels", 0))
        output_channels = int(device.get("max_output_channels", 0))
        kinds = []

        if input_channels:
            kinds.append("input")

        if output_channels:
            kinds.append("output")

        kind = ",".join(kinds) or "-"
        channels = f"{input_channels}/{output_channels}"
        lines.append(f"{index:>5} | {kind:<6} | {channels:<8} | {device.get('name')}")

    return "\n".join(lines)


def _find_device(name: str | None, direction: str) -> int | None:
    if not name:
        return None

    normalized_names = _device_name_candidates(name)
    channel_key = "max_input_channels" if direction == "input" else "max_output_channels"

    for index, device in enumerate(sd.query_devices()):
        device_name = str(device.get("name", ""))
        normalized_device_name = _normalize_device_name(device_name)
        channels = int(device.get(channel_key, 0))

        if channels > 0 and any(candidate in normalized_device_name for candidate in normalized_names):
            return index

    raise AudioDeviceNotFound(
        f"Audio {direction} device containing '{name}' was not found.\n\n{format_devices()}"
    )


def _device_name_candidates(name: str) -> set[str]:
    normalized_name = _normalize_device_name(name)
    without_trailing_digits = re.sub(r"\d+$", "", normalized_name)
    return {candidate for candidate in {normalized_name, without_trailing_digits} if candidate}


def _normalize_device_name(name: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", "", name.lower())
