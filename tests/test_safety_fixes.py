"""A bad settings file, or missing window files, cannot stop the app silently."""

from pathlib import Path

import pytest

from xvoice.config import ConfigError, load_settings


def test_bad_settings_file_is_set_aside_and_defaults_load(tmp_path: Path):
    from xvoice.gui import _set_aside_bad_config

    config = tmp_path / "config.toml"
    config.write_text('bot_id = "abc"\nthreshold = 1.5\n', encoding="utf-8")
    with pytest.raises(ConfigError) as caught:
        load_settings(config)

    notice = _set_aside_bad_config(config, caught.value)

    assert not config.exists()
    backup = tmp_path / "config.toml.invalid"
    assert backup.read_text(encoding="utf-8").startswith('bot_id = "abc"')
    assert "config.toml.invalid" in notice
    # With the bad file moved, the next load is the first-run defaults.
    assert load_settings(config).wake_model == "computer"


def test_settings_window_survives_a_bad_file(tmp_path: Path, monkeypatch):
    import xvoice.gui as gui

    config = tmp_path / "config.toml"
    config.write_text("this is = = not toml", encoding="utf-8")
    seen = {}

    class _Stop(Exception):
        pass

    def fake_tk():
        seen["settings"] = window.settings
        seen["notice"] = window._config_notice
        raise _Stop

    class _TkStub:
        Tk = staticmethod(fake_tk)

    window = gui.SettingsWindow.__new__(gui.SettingsWindow)
    monkeypatch.setattr(gui, "VoiceService", lambda on_status=None: None)
    with pytest.raises(_Stop):
        gui.SettingsWindow.__init__(window, _TkStub, None, config, tmp_path)
    assert seen["settings"].bot_id == ""
    assert "could not be read" in seen["notice"]
    assert (tmp_path / "config.toml.invalid").exists()


def test_missing_tcl_files_message_says_to_extract_again(tmp_path: Path):
    from xvoice.app import fatal_message

    class TclError(Exception):
        pass

    text = fatal_message(TclError("Can't find a usable init.tcl in the following directories"), tmp_path)
    assert "extract the whole download again" in text
    assert str(tmp_path) in text
    assert "extract" not in fatal_message(RuntimeError("other"), tmp_path).lower()


def test_app_icon_is_bundled_and_valid():
    import struct

    from xvoice.gui import app_icon_path

    path = app_icon_path()
    data = path.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1)
    sizes = {data[6 + 16 * i] or 256 for i in range(count)}
    assert {16, 32, 48, 256} <= sizes
    spec = (path.parents[1] / "x-voice.spec").read_text(encoding="utf-8")
    assert 'icon=str(root / "assets" / "x-voice.ico")' in spec
    assert '(str(root / "assets" / "x-voice.ico"), "assets")' in spec


def test_window_icon_failure_never_stops_the_window():
    from xvoice.gui import _apply_window_icon

    class Root:
        def iconbitmap(self, default=None):
            raise RuntimeError("bad icon")

    _apply_window_icon(Root())
