"""Local model paths and microphone selection."""

from pathlib import Path

import pytest

from xvoice.audio import InputDevice, MicNotFound, format_device_message, resolve_input_device
from xvoice.models import ModelMissing, resolve_model_paths
from xvoice.setup_models import SetupError, ensure_models, missing_or_damaged
import xvoice.setup_models as setup_models


DEVICES = [
    InputDevice(0, "Microphone (Realtek)", 2),
    InputDevice(1, "Speakers", 0),
    InputDevice(2, "Headset Microphone", 1),
    InputDevice(3, "Microphone (Realtek USB)", 2),
]


def test_default_mic_is_the_system_device():
    assert resolve_input_device(None, DEVICES) is None


def test_mic_index_and_unique_name():
    assert resolve_input_device(2, DEVICES) == 2
    assert resolve_input_device("headset", DEVICES) == 2


def test_ambiguous_or_missing_mic_lists_inputs_only():
    with pytest.raises(MicNotFound) as ambiguous:
        resolve_input_device("realtek", DEVICES)
    message = str(ambiguous.value)
    assert "0: Microphone (Realtek)" in message
    assert "Speakers" not in message
    with pytest.raises(MicNotFound, match="No microphone was found"):
        resolve_input_device(None, [InputDevice(1, "Speakers", 0)])
    assert "Speakers" not in format_device_message("nope", [InputDevice(1, "Speakers", 0)])


def test_output_device_index_is_not_a_microphone():
    with pytest.raises(MicNotFound):
        resolve_input_device(1, DEVICES)


def _touch_models(directory: Path) -> None:
    for name in ("melspectrogram.onnx", "embedding_model.onnx", "hey_jarvis_v0.1.onnx"):
        (directory / name).write_bytes(b"model")


def test_builtin_model_paths(tmp_path: Path):
    _touch_models(tmp_path)
    paths = resolve_model_paths(tmp_path, "hey_jarvis")
    assert paths.wake.name == "hey_jarvis_v0.1.onnx"
    assert paths.melspec.name == "melspectrogram.onnx"
    assert paths.embedding.name == "embedding_model.onnx"


def test_missing_model_tells_you_to_run_setup(tmp_path: Path):
    with pytest.raises(ModelMissing, match="python -m xvoice.setup_models"):
        resolve_model_paths(tmp_path, "hey_jarvis")


def test_model_name_cannot_escape_the_folder(tmp_path: Path):
    with pytest.raises(ModelMissing, match="file name"):
        resolve_model_paths(tmp_path, "../secret.onnx")


def test_setup_check_does_not_touch_the_network(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(setup_models, "FILES", {"tiny.onnx": "ab" * 32})

    def boom(*args, **kwargs):
        raise AssertionError("setup tried to use the network during --check")

    monkeypatch.setattr(setup_models.urllib.request, "urlopen", boom)
    assert missing_or_damaged(tmp_path) == ["tiny.onnx"]
    with pytest.raises(SetupError, match="python -m xvoice.setup_models"):
        ensure_models(tmp_path, check_only=True)

    payload = b"abc"
    digest = __import__("hashlib").sha256(payload).hexdigest()
    monkeypatch.setattr(setup_models, "FILES", {"tiny.onnx": digest})
    (tmp_path / "tiny.onnx").write_bytes(payload)
    assert missing_or_damaged(tmp_path) == []
    ensure_models(tmp_path, check_only=True)
