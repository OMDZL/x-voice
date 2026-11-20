"""Config validation, including the shipped example file."""

from pathlib import Path

import pytest

from xvoice.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "config.example.toml"


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_example_config_refuses_the_placeholder():
    with pytest.raises(ConfigError, match="PASTE_BOT_ID_HERE"):
        load_config(EXAMPLE)


def test_missing_file_names_the_example(tmp_path: Path):
    with pytest.raises(ConfigError, match="config.example.toml"):
        load_config(tmp_path / "config.toml")


def test_defaults_and_a_real_bot_id(tmp_path: Path):
    path = _write(tmp_path, 'bot_id = "voice-bot-1"\n')
    config = load_config(path)
    assert config.bot_id == "voice-bot-1"
    assert config.wake_model == "hey_jarvis"
    assert config.threshold == 0.5
    assert config.cooldown_seconds == 10
    assert config.mic_device is None
    assert config.chime is False
    assert config.tray is False
    assert config.start_with_windows is False


def test_explicit_settings_round_trip(tmp_path: Path):
    path = _write(
        tmp_path,
        "\n".join(
            [
                'bot_id = "abc"',
                'wake_model = "alexa"',
                "threshold = 0.7",
                "cooldown_seconds = 15",
                "mic_device = 2",
                "chime = true",
                "tray = true",
                "",
            ]
        ),
    )
    config = load_config(path)
    assert config.wake_model == "alexa"
    assert config.threshold == 0.7
    assert config.cooldown_seconds == 15
    assert config.mic_device == 2
    assert config.chime is True
    assert config.tray is True


def test_mic_device_name_and_blank(tmp_path: Path):
    named = load_config(_write(tmp_path, 'bot_id = "abc"\nmic_device = "Realtek"\n'))
    assert named.mic_device == "Realtek"
    blank = load_config(_write(tmp_path, 'bot_id = "abc"\nmic_device = ""\n'))
    assert blank.mic_device is None


def test_empty_bot_id(tmp_path: Path):
    with pytest.raises(ConfigError, match="empty"):
        load_config(_write(tmp_path, 'bot_id = "  "\n'))


def test_whole_link_is_rejected(tmp_path: Path):
    with pytest.raises(ConfigError, match="last part"):
        load_config(_write(tmp_path, 'bot_id = "https://example.invalid/bots/abc"\n'))


def test_bad_threshold_and_cooldown(tmp_path: Path):
    with pytest.raises(ConfigError, match="threshold"):
        load_config(_write(tmp_path, 'bot_id = "abc"\nthreshold = 0\n'))
    with pytest.raises(ConfigError, match="threshold"):
        load_config(_write(tmp_path, 'bot_id = "abc"\nthreshold = 1.2\n'))
    with pytest.raises(ConfigError, match="cooldown"):
        load_config(_write(tmp_path, 'bot_id = "abc"\ncooldown_seconds = -1\n'))


def test_unknown_setting(tmp_path: Path):
    with pytest.raises(ConfigError, match="text"):
        load_config(_write(tmp_path, 'bot_id = "abc"\ntext = "hello"\n'))


def test_chime_must_be_boolean(tmp_path: Path):
    with pytest.raises(ConfigError, match="chime"):
        load_config(_write(tmp_path, 'bot_id = "abc"\nchime = "yes"\n'))
