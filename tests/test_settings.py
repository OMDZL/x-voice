"""Settings persistence, bot-id parsing, validation, and the startup toggle."""

from pathlib import Path

import pytest

from xvoice.audio import (
    MIC_PRIVACY_URI,
    InputDevice,
    device_menu_entries,
    frame_level,
    is_blocked_silence,
    open_microphone_privacy_settings,
    resolve_or_default,
)
from xvoice.config import (
    Config,
    can_listen,
    can_save,
    default_settings,
    load_settings,
    save_settings,
    user_config_path,
)
from xvoice.deeplink import DeepLinkError, extract_bot_id
from xvoice.startup import MemoryRunKey, apply_startup, launch_command, startup_is_enabled

DEVICES = [
    InputDevice(0, "Microphone (Realtek)", 2),
    InputDevice(1, "Speakers", 0),
    InputDevice(2, "Headset Microphone", 1),
    InputDevice(3, "Microphone (Realtek)", 2),
]


def test_user_config_uses_appdata():
    path = user_config_path({"APPDATA": r"C:\Users\Ada\AppData\Roaming"})
    assert path.parts[-2:] == ("x-voice", "config.toml")
    assert "Roaming" in str(path)


def test_user_config_uses_xdg_when_there_is_no_appdata(tmp_path: Path):
    path = user_config_path({"XDG_CONFIG_HOME": str(tmp_path)}, home=tmp_path)
    assert path == tmp_path / "x-voice" / "config.toml"


def test_settings_round_trip(tmp_path: Path):
    path = tmp_path / "config.toml"
    settings = Config(
        bot_id="voice-bot-1",
        wake_model="alexa",
        threshold=0.65,
        cooldown_seconds=12,
        mic_device="Headset Microphone",
        chime=True,
        tray=True,
        start_with_windows=False,
    )
    save_settings(path, settings)
    assert load_settings(path) == settings
    assert path.with_suffix(".toml.tmp").exists() is False


def test_missing_settings_are_the_defaults(tmp_path: Path):
    settings = load_settings(tmp_path / "missing.toml")
    assert settings == default_settings()
    assert settings.bot_id == ""
    assert settings.wake_model == "computer"
    assert settings.threshold == 0.75
    assert settings.trigger_frames == 3
    assert settings.start_with_windows is False
    assert settings.tray is False
    assert can_listen(settings)


def test_placeholder_file_opens_as_unset(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        'bot_id = "PASTE_BOT_ID_HERE"\ntray = true\nchime = true\n',
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.bot_id == ""
    assert settings.tray is True
    assert settings.chime is True
    assert settings.start_with_windows is False


def test_share_link_and_deep_link_keep_only_the_id(tmp_path: Path):
    assert extract_bot_id("  voice-bot-1  ") == "voice-bot-1"
    assert extract_bot_id('"voice-bot-1"') == "voice-bot-1"
    assert extract_bot_id("https://example.invalid/bots/voice-bot-1") == "voice-bot-1"
    assert extract_bot_id("https://example.invalid/bots/voice-bot-1/") == "voice-bot-1"
    deep_link = "grokbot://app/v1/prompt?id=voice-bot-1&text=hello"
    assert extract_bot_id(deep_link) == "voice-bot-1"
    assert "text" not in extract_bot_id(deep_link)

    path = tmp_path / "config.toml"
    path.write_text(f'bot_id = "{deep_link}"\n', encoding="utf-8")
    assert load_settings(path).bot_id == "voice-bot-1"


def test_bad_bot_ids_are_rejected():
    for raw in ("", "   ", "PASTE_BOT_ID_HERE", "hello world", "abc&text=hello", "https://example.invalid/"):
        with pytest.raises(DeepLinkError):
            extract_bot_id(raw)


def test_save_and_listen_rules():
    ready = default_settings()
    assert can_listen(ready)
    saved = Config(
        bot_id="",
        wake_model="hey_jarvis",
        threshold=0.5,
        cooldown_seconds=10,
        mic_device=None,
        chime=False,
        tray=False,
        start_with_windows=False,
    )
    assert can_save(saved) is None
    assert can_listen(saved)
    bad = Config(
        bot_id="voice-bot-1",
        wake_model="not-a-phrase",
        threshold=0,
        cooldown_seconds=-1,
        mic_device=None,
        chime=False,
        tray=False,
        start_with_windows=False,
    )
    assert can_save(bad)
    assert can_listen(bad)


def test_startup_toggle_defaults_off_and_uses_the_user_run_key():
    store = MemoryRunKey()
    assert startup_is_enabled(store) is False
    command = launch_command(r"C:\Program Files\x-voice\x-voice.exe")
    apply_startup(True, command, store)
    assert startup_is_enabled(store) is True
    assert store.get("x-voice") == command
    assert command.startswith('"')
    apply_startup(False, command, store)
    assert startup_is_enabled(store) is False
    with pytest.raises(ValueError):
        apply_startup(True, "  ", store)


def test_launch_command_quotes_arguments():
    command = launch_command(r"C:\Python\python.exe", ["-m", "xvoice"])
    assert "python.exe" in command
    assert "-m" in command
    assert "xvoice" in command


def test_missing_microphone_falls_back_to_the_default():
    chosen, notice = resolve_or_default("Gone Mic", DEVICES[:3])
    assert chosen is None
    assert notice is not None
    assert "Windows default" in notice
    chosen, notice = resolve_or_default("Headset Microphone", DEVICES[:3])
    assert chosen == 2
    assert notice is None


def test_silence_and_level_stay_in_memory():
    assert is_blocked_silence([b"\x00\x00"] * 5) is True
    assert is_blocked_silence([b"\x00\x00"] * 4) is False
    assert is_blocked_silence([b"\x00\x00"] * 5 + [b"\x01\x00"]) is False
    assert frame_level(b"\x00\x00" * 8) == 0
    loud = (32767).to_bytes(2, "little", signed=True) * 8
    assert frame_level(loud) == pytest.approx(1.0, abs=0.001)


def test_duplicate_device_names_stay_distinct():
    entries = device_menu_entries(DEVICES)
    labels = [label for label, _value in entries]
    assert labels[0] == "Windows default"
    assert "Headset Microphone" in labels
    assert any(label.startswith("Microphone (Realtek) (") for label in labels)


def test_custom_model_import_copies_a_real_onnx_and_rejects_junk(tmp_path: Path):
    from xvoice.custom_model import ModelImportError, import_custom_model, list_custom_models
    from xvoice.models import COMPUTER_SHA256, sha256_file

    source = Path(__file__).resolve().parents[1] / "third_party" / "wakewords" / "computer_v2.onnx"
    assert sha256_file(source) == COMPUTER_SHA256
    stored = import_custom_model(source, tmp_path)
    assert stored == "computer_v2.onnx"
    assert sha256_file(tmp_path / stored) == COMPUTER_SHA256
    assert list_custom_models(tmp_path) == ["computer_v2.onnx"]

    text_file = tmp_path / "notes.onnx"
    text_file.write_text("this is not a model\n" * 800, encoding="utf-8")
    with pytest.raises(ModelImportError, match="text"):
        import_custom_model(text_file, tmp_path / "out")

    tiny = tmp_path / "tiny.onnx"
    tiny.write_bytes(b"\x08" * 20)
    with pytest.raises(ModelImportError, match="size"):
        import_custom_model(tiny, tmp_path / "out")

    wrong = tmp_path / "phrase.txt"
    wrong.write_bytes(b"\x08" * 20_000)
    with pytest.raises(ModelImportError, match=".onnx"):
        import_custom_model(wrong, tmp_path / "out")


def test_wake_menu_lists_computer_and_a_custom_file():
    from xvoice.custom_model import CUSTOM_OPTION, wake_menu

    rows = wake_menu(["my_phrase.onnx"])
    labels = [label for label, _value in rows]
    assert labels[0] == "Computer"
    assert "my phrase" in labels
    assert labels[-1] == CUSTOM_OPTION
    assert rows[0][1] == "computer"


def test_privacy_button_target_is_the_windows_microphone_page():
    opened: list[str] = []
    assert open_microphone_privacy_settings(opened.append) == MIC_PRIVACY_URI
    assert opened == ["ms-settings:privacy-microphone"]
