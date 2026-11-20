"""Start the settings window, or the terminal listener for development."""

import argparse
import logging
import sys
import tempfile
import threading
from pathlib import Path

from xvoice import __version__
from xvoice.audio import list_mics
from xvoice.config import (
    ConfigError,
    default_settings,
    load_config,
    load_settings,
    user_config_path,
    user_models_dir,
)
from xvoice.detector import FRAME_SAMPLES
from xvoice.models import (
    COMPUTER_SHA256,
    ModelMissing,
    OpenWakeWordScorer,
    bundled_models_dir,
    load_wake_model,
    resolve_model_paths,
    sha256_file,
)
from xvoice.service import VoiceService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="xvoice",
        description="Listen for a wake phrase and start a Grok Bot voice chat.",
    )
    parser.add_argument("--config", default=None, help="Settings file. Default: the per-user config.")
    parser.add_argument("--models-dir", default=None, help="Wake-word model folder. Default: the bundled models.")
    parser.add_argument("--list-mics", action="store_true", help="Print microphone names and exit.")
    parser.add_argument("--console", action="store_true", help="Run in this terminal instead of the settings window.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Load the bundled model and settings, then exit. Does not open the microphone.",
    )
    args = parser.parse_args(argv)
    _configure_logging()
    models_dir = Path(args.models_dir) if args.models_dir else bundled_models_dir()
    config_path = Path(args.config) if args.config else user_config_path()
    if args.list_mics:
        return list_mics()
    if args.self_test:
        return self_test(models_dir, config_path)
    if args.console:
        return _run_console(config_path, models_dir)
    from xvoice.gui import launch_settings

    try:
        return launch_settings(config_path, models_dir)
    except KeyboardInterrupt:
        print("\nStopped. The microphone is released.")
        return 0
    except Exception as exc:
        _report_fatal(exc)
        return 1


def _report_fatal(exc: Exception) -> None:
    """Log a startup crash and show it, since the windowed exe has no console."""
    logging.exception("x-voice could not start.")
    message = fatal_message(exc, user_config_path().parent)
    if _windows_message_box(message):
        return
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("x-voice", message, parent=root)
        root.destroy()
    except Exception:
        if sys.stderr is not None:
            print(message, file=sys.stderr)


def fatal_message(exc: Exception, log_folder: Path) -> str:
    text = f"x-voice could not start.\n\nDetails: {exc}\n\n"
    if "init.tcl" in str(exc) or "tcl" in type(exc).__name__.lower():
        text += (
            "Files that the settings window needs are missing from the app folder. "
            "Delete the x-voice folder, then extract the whole download again with "
            "Extract All, and run x-voice.exe from the new folder.\n\n"
        )
    return text + f"The log is in {log_folder}."


def _windows_message_box(message: str) -> bool:
    """Show a native Windows error box. It does not need Tcl/Tk."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        MB_ICONERROR = 0x10
        ctypes.windll.user32.MessageBoxW(None, message, "x-voice", MB_ICONERROR)
        return True
    except Exception:
        return False


def self_test(models_dir: Path, config_path: Path) -> int:
    """Load the wake model and the settings file, then exit. The mic stays closed."""
    result_path = Path(tempfile.gettempdir()) / "x-voice-self-test.txt"
    try:
        for wake_model in ("hey_jarvis", "computer"):
            paths = resolve_model_paths(
                models_dir, wake_model, extra_dirs=[user_models_dir()]
            )
            if wake_model == "computer" and sha256_file(paths.wake) != COMPUTER_SHA256:
                raise RuntimeError("The Computer wake model does not match the pinned file.")
            model = load_wake_model(paths)
            scores = OpenWakeWordScorer(model).predict(b"\x00\x00" * FRAME_SAMPLES)
            if not isinstance(scores, dict) or not scores:
                raise RuntimeError(f"The {wake_model} model did not return a score.")
        if config_path.is_file():
            load_settings(config_path)
        else:
            settings = default_settings()
            if settings.wake_model != "computer" or settings.trigger_frames != 3:
                raise RuntimeError("Default settings are unexpected.")
            if settings.start_with_windows or abs(settings.threshold - 0.75) > 0.001:
                raise RuntimeError("Default settings are unexpected.")
        result_path.write_text("ok\n", encoding="utf-8")
        logging.info("self-test ok (%s)", __version__)
        return 0
    except Exception as exc:
        result_path.write_text(f"FAIL {exc}\n", encoding="utf-8")
        logging.error("self-test failed: %s", exc)
        return 1


def _run_console(config_path: Path, models_dir: Path) -> int:
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except ModelMissing as exc:
        print(f"Model error: {exc}", file=sys.stderr)
        return 2
    if config.tray:
        logging.info("The system tray is used by the settings window. This session stays in the terminal.")
    service = VoiceService()
    stop = threading.Event()
    _start_console_controls(service, stop)
    try:
        return service.run_blocking(config, models_dir, stop)
    except KeyboardInterrupt:
        stop.set()
        print("\nStopped. The microphone is released.")
        return 0
    except ModelMissing as exc:
        print(f"Model error: {exc}", file=sys.stderr)
        return 2


def _start_console_controls(service: VoiceService, stop: threading.Event) -> None:
    if sys.stdin is None or not sys.stdin.isatty():
        return

    def _read_commands() -> None:
        while not stop.is_set():
            line = sys.stdin.readline()
            if line == "":
                return
            command = line.strip().lower()
            if command == "p":
                service.pause()
            elif command == "r":
                service.resume()
            elif command == "q":
                stop.set()
            elif command:
                logging.info("Commands: p pauses, r resumes, q quits, Ctrl+C quits.")

    threading.Thread(target=_read_commands, name="xvoice-console", daemon=True).start()


def _configure_logging() -> None:
    handlers: list[logging.Handler] = []
    # A windowed exe has no console, so stderr may be missing.
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    if getattr(sys, "frozen", False):
        folder = user_config_path().parent
        folder.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(folder / "x-voice.log", encoding="utf-8"))
    if not handlers:
        handlers.append(logging.NullHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
