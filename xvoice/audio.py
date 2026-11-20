"""Open the microphone and read 80 ms frames. Frames are not stored on disk."""

import logging
from dataclasses import dataclass

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280


class MicError(Exception):
    """The microphone could not be opened or read."""


class MicNotFound(MicError):
    """config mic_device does not match an input device."""


class MicPermissionError(MicError):
    """Windows is blocking desktop apps from the microphone."""


# Windows privacy page for desktop-app microphone access.
MIC_PRIVACY_URI = "ms-settings:privacy-microphone"

MIC_BLOCKED_MESSAGE = (
    "Windows is not letting x-voice use the microphone. "
    'Turn on "Let desktop apps access your microphone" in Windows microphone settings.'
)

SILENCE_MESSAGE = (
    "The microphone is open, and every sample is silence. "
    "Windows does this when desktop apps are blocked from the microphone. "
    'Turn on "Let desktop apps access your microphone".'
)


@dataclass(frozen=True)
class InputDevice:
    index: int
    name: str
    max_input_channels: int


WINDOWS_DEFAULT_LABEL = "Windows default"


def device_menu_entries(devices: list[InputDevice]) -> list[tuple[str, str | int | None]]:
    """Labels and saved values for the microphone menu.

    The first entry is the Windows default. A repeated device name keeps the
    index so the menu can tell the two devices apart.
    """
    inputs = [device for device in devices if device.max_input_channels > 0]
    folded = [device.name.casefold() for device in inputs]
    entries: list[tuple[str, str | int | None]] = [(WINDOWS_DEFAULT_LABEL, None)]
    for device in inputs:
        if folded.count(device.name.casefold()) == 1:
            entries.append((device.name, device.name))
        else:
            entries.append((f"{device.name} ({device.index})", device.index))
    return entries


def resolve_or_default(
    spec: str | int | None, devices: list[InputDevice]
) -> tuple[int | None, str | None]:
    """Return a device index and a notice when the saved choice is gone.

    None as the index means the Windows default. When the saved device is
    missing and another input exists, the default is used and the notice
    explains that. When nothing can be opened, MicNotFound is raised.
    """
    try:
        return resolve_input_device(spec, devices), None
    except MicNotFound:
        if spec is None:
            raise
        if not any(device.max_input_channels > 0 for device in devices):
            raise
        notice = (
            f"The microphone {spec!r} is no longer available. "
            "x-voice is using the Windows default instead."
        )
        return None, notice


def is_blocked_silence(frames: list[bytes]) -> bool:
    """True when several captured frames are exact zeros.

    A quiet room still has a little noise. A run of all-zero frames is what
    Windows returns when desktop apps are blocked from the microphone.
    The frames are only inspected. They are not stored by this function.
    """
    if len(frames) < 5:
        return False
    for frame in frames:
        if not frame or any(byte != 0 for byte in frame):
            return False
    return True


def frame_level(frame: bytes) -> float:
    """RMS of one int16 frame, scaled to 0..1. The frame is not retained."""
    count = len(frame) // 2
    if count <= 0:
        return 0.0
    total = 0
    for offset in range(0, count * 2, 2):
        sample = int.from_bytes(frame[offset : offset + 2], "little", signed=True)
        total += sample * sample
    rms = (total / count) ** 0.5
    if rms > 32767:
        return 1.0
    return rms / 32767


def open_microphone_privacy_settings(opener=None) -> str:
    """Open the Windows microphone privacy page and return the URI used."""
    if opener is None:
        opener = _open_settings_uri
    opener(MIC_PRIVACY_URI)
    return MIC_PRIVACY_URI


def _open_settings_uri(uri: str) -> None:
    if __import__("sys").platform != "win32":
        raise OSError("Microphone privacy settings are part of Windows.")
    import os

    os.startfile(uri)  # type: ignore[attr-defined]


def resolve_input_device(spec: str | int | None, devices: list[InputDevice]) -> int | None:
    """Return a sounddevice index, or None to keep the system default.

    A string must match one input name, either exactly or as a unique substring.
    Several matches is an error, so a short name cannot pick an arbitrary device.
    """
    inputs = [device for device in devices if device.max_input_channels > 0]
    if spec is None:
        if inputs:
            return None
        raise MicNotFound(format_device_message(spec, devices))
    if isinstance(spec, int):
        if any(device.index == spec and device.max_input_channels > 0 for device in devices):
            return spec
        raise MicNotFound(format_device_message(spec, devices))

    wanted = spec.casefold()
    exact = [device for device in inputs if device.name.casefold() == wanted]
    if len(exact) == 1:
        return exact[0].index
    partial = [device for device in inputs if wanted in device.name.casefold()]
    if len(partial) == 1:
        return partial[0].index
    raise MicNotFound(format_device_message(spec, devices))


def format_device_message(spec: str | int | None, devices: list[InputDevice]) -> str:
    inputs = [device for device in devices if device.max_input_channels > 0]
    if spec is None:
        lines = ["No microphone was found."]
    else:
        lines = [f"Microphone not found for mic_device {spec!r}."]
    if inputs:
        lines.append("Input devices:")
        for device in inputs:
            lines.append(f"  {device.index}: {device.name}")
    else:
        lines.append("No input device was found.")
    lines.append(
        "Leave mic_device empty to use the Windows default, or set it to one of "
        "these indexes or names. Run: python -m xvoice --list-mics"
    )
    return "\n".join(lines)


def query_input_devices() -> list[InputDevice]:
    """Ask PortAudio for the device list. This does not start a recording."""
    import sounddevice as sd

    found: list[InputDevice] = []
    for position, info in enumerate(sd.query_devices()):
        index = int(info["index"]) if "index" in info else position
        found.append(
            InputDevice(
                index=index,
                name=str(info["name"]),
                max_input_channels=int(info["max_input_channels"]),
            )
        )
    return found


def list_mics() -> int:
    """Print input devices and return 0, or 1 when none can be listed."""
    try:
        devices = query_input_devices()
    except Exception as exc:
        logging.error("Could not list microphones. Details: %s", exc)
        print(
            "Could not list microphones. Check that a microphone is plugged in "
            "and that Windows allows this app to use it."
        )
        print(f"Details: {exc}")
        return 1
    inputs = [device for device in devices if device.max_input_channels > 0]
    if not inputs:
        print("No microphone was found.")
        print("Plug one in, allow microphone access in Windows, and run this command again.")
        return 1
    print("Input devices:")
    for device in inputs:
        print(f"  {device.index}: {device.name}")
    print()
    print("Leave mic_device empty in config.toml to use the Windows default.")
    print("Or set mic_device to an index number, or to part of a device name.")
    return 0


class Microphone:
    """A 16 kHz mono int16 capture that yields one 80 ms frame per read."""

    def __init__(self, device: str | int | None, frame_samples: int = FRAME_SAMPLES) -> None:
        self.device_spec = device
        self.frame_samples = frame_samples
        self._stream = None

    def __enter__(self) -> "Microphone":
        import sounddevice as sd

        try:
            resolved = resolve_input_device(self.device_spec, query_input_devices())
        except MicNotFound:
            raise
        except Exception as exc:
            raise MicError(
                "Could not list microphones. Check that a microphone is plugged in "
                "and that Windows allows this app to use it. "
                f"Details: {exc}"
            ) from exc
        try:
            self._stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=self.frame_samples,
                device=resolved,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            raise MicError(
                "Could not open the microphone at 16000 Hz. Check Windows microphone "
                "permission, and try another mic_device in config.toml. "
                f"Details: {exc}"
            ) from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.stop()
        finally:
            stream.close()

    def read_frame(self) -> bytes:
        if self._stream is None:
            raise MicError("The microphone is not open.")
        data, overflowed = self._stream.read(self.frame_samples)
        if overflowed:
            logging.warning("The microphone dropped some audio. A phrase in that gap can be missed.")
        # Copy out of the driver buffer. The copy is the caller's frame and
        # is not written anywhere by this function.
        frame = bytes(data)
        expected = self.frame_samples * 2
        if len(frame) != expected:
            raise MicError(f"Expected {expected} audio bytes from the microphone, got {len(frame)}.")
        return frame
