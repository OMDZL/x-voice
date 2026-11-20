"""Load and save the per-user settings.

The desktop app stores them in %APPDATA%\\x-voice\\config.toml. A missing bot
id is allowed there so the settings window can open on first run. The console
loader still refuses to listen until the id is real.
"""

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from xvoice.deeplink import PLACEHOLDER_BOT_ID, DeepLinkError, build_prompt_link, extract_bot_id
from xvoice.custom_model import is_safe_onnx_name
from xvoice.models import PRETRAINED_MODELS, recommended_trigger_frames

ALLOWED_KEYS = (
    "bot_id",
    "wake_model",
    "threshold",
    "cooldown_seconds",
    "mic_device",
    "chime",
    "tray",
    "start_with_windows",
    "trigger_frames",
)

DEFAULT_WAKE_MODEL = "hey_jarvis"
DEFAULT_THRESHOLD = 0.5
DEFAULT_COOLDOWN_SECONDS = 10.0


class ConfigError(Exception):
    """config.toml is missing or not usable."""


@dataclass(frozen=True)
class Config:
    bot_id: str
    wake_model: str
    threshold: float
    cooldown_seconds: float
    mic_device: str | int | None
    chime: bool
    tray: bool
    start_with_windows: bool = False
    trigger_frames: int = 1


def default_settings() -> Config:
    """First-run desktop settings. The phrase is Computer."""
    return Config(
        bot_id="",
        wake_model="computer",
        threshold=0.75,
        cooldown_seconds=DEFAULT_COOLDOWN_SECONDS,
        mic_device=None,
        chime=False,
        tray=False,
        start_with_windows=False,
        trigger_frames=3,
    )


def user_config_path(environ: dict[str, str] | None = None, home: Path | None = None) -> Path:
    """Where the desktop app reads and writes settings.

    On Windows this is %APPDATA%\\x-voice\\config.toml. Elsewhere it is under
    the XDG config home, which keeps development and tests off the Windows path.
    """
    env = os.environ if environ is None else environ
    appdata = env.get("APPDATA", "").strip()
    if appdata:
        return Path(appdata) / "x-voice" / "config.toml"
    base = home if home is not None else Path.home()
    xdg = env.get("XDG_CONFIG_HOME", "").strip()
    root = Path(xdg) if xdg else base / ".config"
    return root / "x-voice" / "config.toml"


def user_models_dir(environ: dict[str, str] | None = None, home: Path | None = None) -> Path:
    """Folder for a wake model the owner picked in the settings window."""
    return user_config_path(environ, home).parent / "models"


def load_config(path: Path) -> Config:
    """Load settings for the console. A missing or placeholder bot id is an error."""
    if not path.is_file():
        raise ConfigError(
            f"Could not find {path}. Copy config.example.toml to config.toml, "
            "then set bot_id to the id from your voice bot's share link."
        )
    data = _read_toml(path)
    return _build(data, path, require_bot=True)


def load_settings(path: Path) -> Config:
    """Load the desktop settings. A missing file returns the defaults.

    A pasted share link in bot_id is reduced to the id. The placeholder and an
    empty id become an empty id so the settings window can open.
    """
    if not path.is_file():
        return default_settings()
    data = _read_toml(path)
    raw = data.get("bot_id", "")
    if not isinstance(raw, str) or not raw.strip() or raw.strip() == PLACEHOLDER_BOT_ID:
        data = dict(data)
        data["bot_id"] = "pending-bot"
        built = _build(data, path, require_bot=True)
        return replace(built, bot_id="")
    if _looks_like_link(raw):
        data = dict(data)
        data["bot_id"] = extract_bot_id(raw)
    return _build(data, path, require_bot=True)


def save_settings(path: Path, settings: Config) -> None:
    """Write settings atomically. The bot id stored here is the bare id."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = settings_to_toml(settings)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def settings_to_toml(settings: Config) -> str:
    if settings.mic_device is None:
        mic_line = 'mic_device = ""'
    elif isinstance(settings.mic_device, int) and not isinstance(settings.mic_device, bool):
        mic_line = f"mic_device = {settings.mic_device}"
    else:
        mic_line = f"mic_device = {_toml_string(str(settings.mic_device))}"
    lines = [
        f"bot_id = {_toml_string(settings.bot_id)}",
        f"wake_model = {_toml_string(settings.wake_model)}",
        f"threshold = {_toml_number(settings.threshold)}",
        f"cooldown_seconds = {_toml_number(settings.cooldown_seconds)}",
        mic_line,
        f"chime = {_toml_bool(settings.chime)}",
        f"tray = {_toml_bool(settings.tray)}",
        f"start_with_windows = {_toml_bool(settings.start_with_windows)}",
        f"trigger_frames = {int(settings.trigger_frames)}",
        "",
    ]
    return "\n".join(lines)


def can_save(settings: Config) -> str | None:
    """Return a problem that should block saving, or None.

    An empty bot id can be saved. Listening stays off until an id is present.
    """
    if settings.wake_model not in PRETRAINED_MODELS and not is_safe_onnx_name(settings.wake_model):
        return (
            "Choose a wake phrase, or a custom .onnx file. Built-in phrases: "
            + ", ".join(PRETRAINED_MODELS)
            + "."
        )
    if not 1 <= int(settings.trigger_frames) <= 20:
        return "The phrase must be heard for 1 to 20 scores in a row."
    if not 0 < settings.threshold <= 1:
        return "Sensitivity must be greater than 0 and at most 1."
    if settings.cooldown_seconds < 0:
        return "Cooldown must be zero or more seconds."
    if settings.bot_id:
        try:
            build_prompt_link(settings.bot_id)
        except DeepLinkError as exc:
            return str(exc)
    return None


def can_listen(settings: Config) -> str | None:
    """Return why listening cannot start, or None when the settings are ready."""
    if not settings.bot_id:
        return "Enter the bot id, or paste the bot's share link."
    return can_save(settings)


def _read_toml(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain settings, not a single value.")
    unknown = sorted(set(data) - set(ALLOWED_KEYS))
    if unknown:
        allowed = ", ".join(ALLOWED_KEYS)
        names = ", ".join(unknown)
        raise ConfigError(f"Unknown setting(s) in {path}: {names}. Allowed settings: {allowed}.")
    return data


def _build(data: dict, path: Path, require_bot: bool) -> Config:
    bot_id = _bot_id(data, path) if require_bot or "bot_id" in data else ""
    wake_model = _wake_model(data.get("wake_model", DEFAULT_WAKE_MODEL))
    if "trigger_frames" in data:
        trigger_frames = int(
            _number(data["trigger_frames"], "trigger_frames", low=1, high=20)
        )
    else:
        trigger_frames = recommended_trigger_frames(wake_model)
    return Config(
        bot_id=bot_id,
        wake_model=wake_model,
        threshold=_number(
            data.get("threshold", DEFAULT_THRESHOLD),
            "threshold",
            low_exclusive=0,
            high=1,
        ),
        cooldown_seconds=_number(
            data.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS),
            "cooldown_seconds",
            low=0,
            high=None,
        ),
        mic_device=_mic_device(data.get("mic_device", "")),
        chime=_bool(data.get("chime", False), "chime"),
        tray=_bool(data.get("tray", False), "tray"),
        start_with_windows=_bool(data.get("start_with_windows", False), "start_with_windows"),
        trigger_frames=trigger_frames,
    )


def _bot_id(data: dict, path: Path) -> str:
    if "bot_id" not in data:
        raise ConfigError(
            f"{path} needs a bot_id. Copy the id from the end of the bot's share link."
        )
    value = data["bot_id"]
    if not isinstance(value, str):
        raise ConfigError("bot_id must be text, in quotes.")
    cleaned = value.strip()
    if not cleaned:
        raise ConfigError("bot_id is empty. Paste the id from the bot's share link.")
    if cleaned == PLACEHOLDER_BOT_ID:
        raise ConfigError(
            "bot_id is still PASTE_BOT_ID_HERE. Open config.toml and paste the id "
            "from the bot's share link. x-voice will not start until that is changed."
        )
    if _looks_like_link(cleaned):
        raise ConfigError(
            "bot_id looks like a whole link. Paste only the last part of the share link, "
            "after the final slash."
        )
    return cleaned


def _looks_like_link(value: str) -> bool:
    text = value.strip()
    return "://" in text or "/" in text or "\\" in text or "?" in text


def _wake_model(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            "wake_model must be a model name such as hey_jarvis, alexa, "
            "hey_mycroft, hey_rhasspy, timer, or weather."
        )
    return value.strip()


def _number(
    value: object,
    name: str,
    low: float | None = None,
    low_exclusive: float | None = None,
    high: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number.")
    number = float(value)
    if low is not None and number < low:
        raise ConfigError(f"{name} must be at least {low}.")
    if low_exclusive is not None and number <= low_exclusive:
        raise ConfigError(f"{name} must be greater than {low_exclusive}.")
    if high is not None and number > high:
        raise ConfigError(f"{name} must be at most {high}.")
    return number


def _bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{name} must be true or false.")
    return value


def _mic_device(value: object) -> str | int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ConfigError("mic_device must be empty, a device index, or a device name.")
    if isinstance(value, int):
        if value < 0:
            raise ConfigError("mic_device index must be zero or greater.")
        return value
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    raise ConfigError("mic_device must be empty, a device index, or a device name.")


def _toml_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _toml_number(value: float) -> str:
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"
