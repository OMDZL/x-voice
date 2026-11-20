"""The runtime must not fetch models, and Windows libraries stay lazy."""

import sys
from pathlib import Path

from xvoice.chime import play_chime

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = [
    path
    for path in (ROOT / "xvoice").glob("*.py")
    if path.name != "setup_models.py"
]
FORBIDDEN = ("https://", "http://", "urlopen", "download_models", "requests.get", "requests.")


def test_runtime_sources_have_no_network_calls():
    for path in RUNTIME_FILES:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in text, f"{path.name} contains {token}"


def test_app_import_does_not_load_windows_or_model_packages():
    for name in list(sys.modules):
        if name == "xvoice" or name.startswith("xvoice."):
            del sys.modules[name]
    for name in ("pywinauto", "sounddevice", "openwakeword", "winsound", "pystray", "PIL", "tkinter"):
        sys.modules.pop(name, None)

    import xvoice.app  # noqa: F401

    assert "xvoice.setup_models" not in sys.modules
    assert "xvoice.gui" not in sys.modules
    assert "pywinauto" not in sys.modules
    assert "sounddevice" not in sys.modules
    assert "openwakeword" not in sys.modules
    assert "winsound" not in sys.modules
    assert "pystray" not in sys.modules
    assert "PIL" not in sys.modules
    assert "tkinter" not in sys.modules


def test_disabled_chime_does_not_import_winsound():
    sys.modules.pop("winsound", None)
    play_chime(False)
    assert "winsound" not in sys.modules


def test_lockfile_pins_every_requirement():
    requirement_names = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "==" not in stripped:
            continue
        requirement_names.append(stripped.split("==", 1)[0])
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    for name in requirement_names:
        assert f"{name}==" in lock
        assert "--hash=sha256:" in lock.split(f"{name}==", 1)[1].split("\n\n", 1)[0]
    assert requirement_names, "requirements.txt has no pins"
