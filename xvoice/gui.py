"""Settings window. Tkinter is imported here so tests can skip this module."""

from __future__ import annotations

import logging
import queue
import threading
from pathlib import Path

from xvoice import __version__
from xvoice.audio import (
    MIC_BLOCKED_MESSAGE,
    SILENCE_MESSAGE,
    WINDOWS_DEFAULT_LABEL,
    MicError,
    Microphone,
    device_menu_entries,
    frame_level,
    is_blocked_silence,
    open_microphone_privacy_settings,
    query_input_devices,
    resolve_or_default,
)
from xvoice.config import (
    Config,
    ConfigError,
    can_listen,
    can_save,
    default_settings,
    load_settings,
    save_settings,
    user_models_dir,
)
from xvoice.custom_model import (
    CUSTOM_OPTION,
    ModelImportError,
    import_custom_model,
    list_custom_models,
    wake_menu,
)
from xvoice.deeplink import PLACEHOLDER_BOT_ID, DeepLinkError, extract_bot_id
from xvoice.models import (
    PRETRAINED_MODELS,
    recommended_threshold,
    recommended_trigger_frames,
    spoken_phrase,
)
from xvoice.service import VoiceService
from xvoice.startup import apply_user_startup
from xvoice.tray import start_tray, stop_tray, update_tray


# How often the window picks up work from other threads.
DRAIN_MS = 50


def launch_settings(config_path: Path, models_dir: Path) -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:
        print(f"The settings window could not start. Details: {exc}")
        return 2
    window = SettingsWindow(tk, ttk, config_path, models_dir)
    window.run()
    return 0


class SettingsWindow:
    def __init__(self, tk, ttk, config_path: Path, models_dir: Path) -> None:
        self.tk = tk
        self.ttk = ttk
        self.config_path = config_path
        self.models_dir = models_dir
        self._config_notice = ""
        # Work handed over from other threads (listener, mic test, tray). Only
        # the Tk thread touches widgets, and no thread ever waits for it.
        self._pending: queue.SimpleQueue = queue.SimpleQueue()
        self._closing = False
        try:
            self.settings = load_settings(config_path)
        except ConfigError as exc:
            self.settings = default_settings()
            self._config_notice = _set_aside_bad_config(config_path, exc)
        self._trigger_frames = self.settings.trigger_frames
        self._applied_model = self.settings.wake_model
        self._previous_wake_label = ""
        self.service = VoiceService(on_status=self._on_status)
        self.tray_icon = None
        self._probing = False
        self._mic_by_label: dict[str, str | int | None] = {WINDOWS_DEFAULT_LABEL: None}
        self._wake_by_label: dict[str, str] = {}

        self.root = tk.Tk()
        self.root.title(f"x-voice {__version__}")
        _apply_window_icon(self.root)
        self.root.minsize(520, 620)
        self.root.columnconfigure(0, weight=1)

        self.bot_var = tk.StringVar(value=self.settings.bot_id)
        initial_label = (
            spoken_phrase(self.settings.wake_model)
            if self.settings.wake_model in PRETRAINED_MODELS
            else ""
        )
        self.wake_var = tk.StringVar(value=initial_label)
        self.mic_var = tk.StringVar(value=WINDOWS_DEFAULT_LABEL)
        self.threshold_var = tk.DoubleVar(value=self.settings.threshold)
        self.cooldown_var = tk.DoubleVar(value=self.settings.cooldown_seconds)
        self.chime_var = tk.BooleanVar(value=self.settings.chime)
        self.tray_var = tk.BooleanVar(value=self.settings.tray)
        self.startup_var = tk.BooleanVar(value=self.settings.start_with_windows)
        self.threshold_text = tk.StringVar()
        self.cooldown_text = tk.StringVar()
        self.status_var = tk.StringVar(value="Add the Grok Bot id to start listening.")

        self._build()
        self._reload_mics()
        self._select_saved_mic()
        self._sync_slider_labels()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(DRAIN_MS, self._drain)
        self._show_startup()
        if self._config_notice:
            self.status_var.set(self._config_notice)

    def run(self) -> None:
        self.root.mainloop()

    def _build(self) -> None:
        tk = self.tk
        ttk = self.ttk
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="x-voice", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            frame,
            text="Say the wake phrase. x-voice opens your voice bot and starts the call.",
            wraplength=460,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Label(frame, text="Wake phrase").grid(row=2, column=0, sticky="w", pady=4)
        self.wake_box = ttk.Combobox(
            frame,
            textvariable=self.wake_var,
            state="readonly",
            width=36,
        )
        self.wake_box.grid(row=2, column=1, sticky="ew", pady=4)
        self.wake_box.bind("<<ComboboxSelected>>", self._on_wake_selected)
        self._rebuild_wake_menu()
        self.wake_var.set(self._label_for_model(self.settings.wake_model))
        self._previous_wake_label = self.wake_var.get()

        ttk.Label(frame, text="Grok Bot id").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.bot_var, width=40).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(
            frame,
            text="Paste the id, or the whole share link. The link's id is saved on its own.",
            wraplength=320,
        ).grid(row=4, column=1, sticky="w")

        ttk.Label(frame, text="Microphone").grid(row=5, column=0, sticky="w", pady=4)
        mic_row = ttk.Frame(frame)
        mic_row.grid(row=5, column=1, sticky="ew", pady=4)
        mic_row.columnconfigure(0, weight=1)
        self.mic_box = ttk.Combobox(mic_row, textvariable=self.mic_var, state="readonly", width=28)
        self.mic_box.grid(row=0, column=0, sticky="ew")
        ttk.Button(mic_row, text="Refresh", command=self._reload_mics).grid(row=0, column=1, padx=(8, 0))

        meter_row = ttk.Frame(frame)
        meter_row.grid(row=6, column=1, sticky="ew", pady=(0, 8))
        self.test_button = ttk.Button(meter_row, text="Test mic", command=self._test_mic)
        self.test_button.grid(row=0, column=0, sticky="w")
        self.meter = tk.Canvas(meter_row, height=18, width=240, bg="#eceff1", highlightthickness=0)
        self.meter.grid(row=0, column=1, padx=(8, 0), sticky="ew")
        meter_row.columnconfigure(1, weight=1)
        self.meter_bar = self.meter.create_rectangle(0, 0, 0, 18, fill="#2e7d32", width=0)

        ttk.Label(frame, text="How sure").grid(row=7, column=0, sticky="w", pady=4)
        sure = ttk.Frame(frame)
        sure.grid(row=7, column=1, sticky="ew", pady=4)
        sure.columnconfigure(0, weight=1)
        tk.Scale(
            sure,
            from_=0.1,
            to=0.95,
            resolution=0.05,
            orient="horizontal",
            showvalue=False,
            variable=self.threshold_var,
            command=lambda _value: self._sync_slider_labels(),
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(sure, textvariable=self.threshold_text, width=6).grid(row=0, column=1)
        ttk.Label(frame, text="Higher ignores more noise from a TV or a video.", wraplength=320).grid(
            row=8, column=1, sticky="w"
        )

        ttk.Label(frame, text="Cooldown").grid(row=9, column=0, sticky="w", pady=4)
        cool = ttk.Frame(frame)
        cool.grid(row=9, column=1, sticky="ew", pady=4)
        cool.columnconfigure(0, weight=1)
        tk.Scale(
            cool,
            from_=0,
            to=60,
            resolution=1,
            orient="horizontal",
            showvalue=False,
            variable=self.cooldown_var,
            command=lambda _value: self._sync_slider_labels(),
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(cool, textvariable=self.cooldown_text, width=10).grid(row=0, column=1)
        ttk.Label(frame, text="Seconds to wait after a call or a missed click.", wraplength=320).grid(
            row=10, column=1, sticky="w"
        )

        ttk.Checkbutton(frame, text="Play a chime when the phrase is accepted", variable=self.chime_var).grid(
            row=11, column=0, columnspan=2, sticky="w", pady=(12, 2)
        )
        ttk.Checkbutton(frame, text="Show in the system tray", variable=self.tray_var).grid(
            row=12, column=0, columnspan=2, sticky="w", pady=2
        )
        ttk.Checkbutton(frame, text="Start with Windows", variable=self.startup_var).grid(
            row=13, column=0, columnspan=2, sticky="w", pady=2
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=14, column=0, columnspan=2, sticky="ew", pady=(16, 8))
        ttk.Button(buttons, text="Save", command=self._save).grid(row=0, column=0, padx=(0, 8))
        self.pause_button = ttk.Button(buttons, text="Pause", command=self._toggle_pause)
        self.pause_button.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(buttons, text="Quit", command=self._quit).grid(row=0, column=2)
        self.privacy_button = ttk.Button(
            buttons,
            text="Open microphone settings",
            command=self._open_privacy,
        )

        ttk.Label(frame, textvariable=self.status_var, wraplength=480).grid(
            row=15, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

    def _show_startup(self) -> None:
        needs_id = can_listen(self.settings) is not None
        if self.settings.tray:
            self._sync_tray()
        if needs_id or not self.settings.tray:
            self.root.deiconify()
            if needs_id:
                self.status_var.set("Enter the bot id, or paste the bot's share link.")
        else:
            self.root.withdraw()
        if not needs_id:
            self.service.start(self.settings, self.models_dir)

    def _rebuild_wake_menu(self) -> None:
        rows = wake_menu(list_custom_models(user_models_dir()))
        self._wake_by_label = {label: value for label, value in rows if value != CUSTOM_OPTION}
        self.wake_box.configure(values=[label for label, _value in rows])

    def _label_for_model(self, wake_model: str) -> str:
        for label, value in self._wake_by_label.items():
            if value == wake_model:
                return label
        if wake_model in PRETRAINED_MODELS:
            return spoken_phrase(wake_model)
        return spoken_phrase("computer")

    def _on_wake_selected(self, _event=None) -> None:
        label = self.wake_var.get()
        if label == CUSTOM_OPTION:
            self._pick_custom_model()
            return
        model = self._wake_by_label.get(label, "")
        if model and model != self._applied_model:
            self.threshold_var.set(recommended_threshold(model))
            self._trigger_frames = recommended_trigger_frames(model)
            self._applied_model = model
            self._sync_slider_labels()
        self._previous_wake_label = label

    def _pick_custom_model(self) -> None:
        from tkinter import filedialog

        chosen = filedialog.askopenfilename(
            parent=self.root,
            title="Choose a wake word model",
            filetypes=[("ONNX wake word", "*.onnx")],
        )
        if not chosen:
            self.wake_var.set(self._previous_wake_label or self._label_for_model("computer"))
            return
        try:
            filename = import_custom_model(Path(chosen), user_models_dir())
        except ModelImportError as exc:
            self.status_var.set(str(exc))
            self.wake_var.set(self._previous_wake_label or self._label_for_model("computer"))
            return
        self._rebuild_wake_menu()
        self.wake_var.set(self._label_for_model(filename))
        self._previous_wake_label = self.wake_var.get()
        self._applied_model = filename
        self._trigger_frames = 1
        self.threshold_var.set(recommended_threshold(filename))
        self._sync_slider_labels()
        self.status_var.set(f"Added {filename}. Click Save to use it.")

    def _sync_slider_labels(self) -> None:
        self.threshold_text.set(f"{float(self.threshold_var.get()):.2f}")
        self.cooldown_text.set(f"{int(float(self.cooldown_var.get()))} sec")

    def _reload_mics(self) -> None:
        try:
            devices = query_input_devices()
        except Exception as exc:
            devices = []
            self.status_var.set(f"Could not list microphones. Details: {exc}")
        entries = device_menu_entries(devices)
        self._mic_by_label = {label: value for label, value in entries}
        self.mic_box.configure(values=[label for label, _value in entries])
        if self.mic_var.get() not in self._mic_by_label:
            self.mic_var.set(WINDOWS_DEFAULT_LABEL)

    def _select_saved_mic(self) -> None:
        saved = self.settings.mic_device
        if saved is None:
            self.mic_var.set(WINDOWS_DEFAULT_LABEL)
            return
        for label, value in self._mic_by_label.items():
            if value == saved:
                self.mic_var.set(label)
                return
        label = str(saved)
        self._mic_by_label[label] = saved
        values = list(self.mic_box.cget("values"))
        self.mic_box.configure(values=[*values, label])
        self.mic_var.set(label)

    def _collect(self) -> Config:
        raw_bot = self.bot_var.get().strip()
        if not raw_bot or raw_bot == PLACEHOLDER_BOT_ID:
            bot_id = ""
        else:
            bot_id = extract_bot_id(raw_bot)
        wake_model = self._wake_by_label.get(self.wake_var.get(), "")
        mic = self._mic_by_label.get(self.mic_var.get(), self.mic_var.get())
        if mic == "":
            mic = None
        return Config(
            bot_id=bot_id,
            wake_model=wake_model,
            threshold=round(float(self.threshold_var.get()), 2),
            cooldown_seconds=float(int(float(self.cooldown_var.get()))),
            mic_device=mic,
            chime=bool(self.chime_var.get()),
            tray=bool(self.tray_var.get()),
            start_with_windows=bool(self.startup_var.get()),
            trigger_frames=int(self._trigger_frames),
        )

    def _save(self) -> None:
        try:
            settings = self._collect()
        except DeepLinkError as exc:
            self.status_var.set(str(exc))
            return
        problem = can_save(settings)
        if problem:
            self.status_var.set(problem)
            return
        save_settings(self.config_path, settings)
        self.settings = settings
        self.bot_var.set(settings.bot_id)
        try:
            apply_user_startup(settings.start_with_windows)
        except OSError as exc:
            self.status_var.set(str(exc))
            return
        self._sync_tray()
        listen_problem = can_listen(settings)
        if listen_problem:
            self.service.stop()
            self.status_var.set(listen_problem)
            self.root.deiconify()
            return
        self.service.start(settings, self.models_dir)
        self.status_var.set("Saved. Listening with these settings.")

    def _toggle_pause(self) -> None:
        if self.service.paused:
            self.service.resume()
            if not self.service.running and can_listen(self.settings) is None:
                self.service.start(self.settings, self.models_dir)
        else:
            self.service.pause()
        self._refresh_pause_button()
        self._update_tray_icon()

    def _refresh_pause_button(self) -> None:
        self.pause_button.configure(text="Resume" if self.service.paused else "Pause")

    def _test_mic(self) -> None:
        if self._probing:
            return
        self._probing = True
        self.test_button.configure(state="disabled")
        spec = self._mic_by_label.get(self.mic_var.get())
        threading.Thread(target=self._probe, args=(spec,), name="xvoice-mic-test", daemon=True).start()

    def _probe(self, spec) -> None:
        was_paused = self.service.paused
        self.service.stop(announce=False)
        error = None
        try:
            devices = query_input_devices()
            chosen, notice = resolve_or_default(spec, devices)
            frames: list[bytes] = []
            with Microphone(chosen) as mic:
                for _ in range(16):
                    frame = mic.read_frame()
                    frames.append(frame)
                    level = frame_level(frame)
                    self._call_soon(lambda value=level: self._set_level(value))
            if notice:
                self._call_soon(lambda: self._remember_default_mic(notice))
            elif is_blocked_silence(frames):
                error = SILENCE_MESSAGE
        except MicError as exc:
            error = f"{MIC_BLOCKED_MESSAGE} Details: {exc}"
        except Exception as exc:
            error = f"{MIC_BLOCKED_MESSAGE} Details: {exc}"

        def finish() -> None:
            self._probing = False
            self.test_button.configure(state="normal")
            self._set_level(0)
            if error:
                self.status_var.set(error)
                self._show_privacy(True)
            if can_listen(self.settings) is None and not was_paused:
                self.service.start(self.settings, self.models_dir)

        self._call_soon(finish)

    def _remember_default_mic(self, notice: str) -> None:
        self.mic_var.set(WINDOWS_DEFAULT_LABEL)
        self.status_var.set(notice)
        try:
            settings = self._collect()
        except DeepLinkError:
            return
        if can_save(settings) is None:
            save_settings(self.config_path, settings)
            self.settings = settings

    def _set_level(self, level: float) -> None:
        width = max(0, int(self.meter.winfo_width() * max(0.0, min(1.0, level))))
        height = max(18, self.meter.winfo_height())
        self.meter.coords(self.meter_bar, 0, 0, width, height)

    def _open_privacy(self) -> None:
        try:
            open_microphone_privacy_settings()
        except OSError as exc:
            self.status_var.set(str(exc))

    def _show_privacy(self, visible: bool) -> None:
        if visible:
            self.privacy_button.grid(row=0, column=3, padx=(8, 0))
        else:
            self.privacy_button.grid_remove()

    def _on_status(self, state: str, detail: str) -> None:
        self._call_soon(lambda: self._apply_status(state, detail))

    def _apply_status(self, state: str, detail: str) -> None:
        if detail:
            self.status_var.set(detail)
        if "no longer available" in detail:
            self._remember_default_mic(detail)
        self._show_privacy(state == "permission")
        self._refresh_pause_button()
        self._update_tray_icon()

    def _sync_tray(self) -> None:
        try:
            if self.settings.tray and self.tray_icon is None:
                self.tray_icon = start_tray(
                    on_open=lambda: self._call_soon(self._show),
                    on_toggle_pause=lambda: self._call_soon(self._toggle_pause),
                    on_quit=lambda: self._call_soon(self._quit),
                    is_paused=lambda: self.service.paused,
                    state="paused" if self.service.paused else self.service.state,
                )
            elif not self.settings.tray and self.tray_icon is not None:
                stop_tray(self.tray_icon)
                self.tray_icon = None
        except Exception as exc:
            self.status_var.set(f"The tray icon could not start. Details: {exc}")

    def _update_tray_icon(self) -> None:
        state = "paused" if self.service.paused else self.service.state
        update_tray(self.tray_icon, state, self.service.paused)

    def _show(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def _on_close(self) -> None:
        if self.settings.tray and self.tray_icon is not None:
            self.root.withdraw()
            return
        self._quit()

    def _call_soon(self, action) -> None:
        """Run `action` on the Tk thread. Safe from any thread; never blocks."""
        if not self._closing:
            self._pending.put(action)

    def _drain(self) -> None:
        while True:
            try:
                action = self._pending.get_nowait()
            except queue.Empty:
                break
            try:
                action()
            except Exception:
                logging.exception("A window update failed.")
            if self._closing:
                return
        if not self._closing:
            self.root.after(DRAIN_MS, self._drain)

    def _quit(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.service.stop()
        stop_tray(self.tray_icon)
        self.tray_icon = None
        self.root.destroy()


def _set_aside_bad_config(config_path: Path, error: ConfigError) -> str:
    """Rename an unreadable settings file so the window can open on defaults.

    The old file is kept beside the new one so nothing the owner typed is lost.
    """
    logging.error("Settings file could not be read: %s", error)
    backup = config_path.with_name(config_path.name + ".invalid")
    try:
        config_path.replace(backup)
    except OSError as exc:
        logging.error("Could not move the settings file aside: %s", exc)
        return (
            f"The saved settings could not be read, so defaults are shown. Details: {error} "
            "Click Save to replace that file."
        )
    return (
        f"The saved settings could not be read, so defaults are shown. Details: {error} "
        f"The old file was kept as {backup.name}. Fill in the settings and click Save."
    )


def app_icon_path() -> Path:
    """The x-voice .ico, beside a frozen app or in the checkout's assets folder."""
    import sys

    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "assets" / "x-voice.ico"
    return Path(__file__).resolve().parent.parent / "assets" / "x-voice.ico"


def _apply_window_icon(root) -> None:
    """Use the x-voice icon for this window and any dialog it opens.

    A missing or unreadable icon keeps Tk's default. It never stops the window.
    """
    path = app_icon_path()
    if not path.is_file():
        return
    try:
        root.iconbitmap(default=str(path))
    except Exception as exc:
        logging.info("The window icon could not be set: %s", exc)
