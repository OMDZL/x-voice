"""Background listener used by the settings window and the console.

Audio frames are scored in memory and dropped. This module does not write
them, log them, or send them anywhere.
"""

import logging
import threading
import time
from pathlib import Path

from xvoice.audio import (
    MIC_BLOCKED_MESSAGE,
    SILENCE_MESSAGE,
    MicError,
    Microphone,
    is_blocked_silence,
    query_input_devices,
    resolve_or_default,
)
from xvoice.automator import call_ui_visible, start_voice_chat, wait_for_grok_window
from xvoice.chime import play_chime
from xvoice.config import Config, user_models_dir
from xvoice.deeplink import DeepLinkError
from xvoice.detector import WakeListener
from xvoice.guard import Phase, SessionGuard
from xvoice.launcher import open_prompt_link
from xvoice.models import OpenWakeWordScorer, load_wake_model, resolve_model_paths, spoken_phrase

class VoiceService:
    """Runs the wake-word loop on a daemon thread and reports status."""

    def __init__(self, on_status=None) -> None:
        self._on_status = on_status
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._guard: SessionGuard | None = None
        self.paused = False
        self.state = "idle"
        self.detail = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, config: Config, models_dir: Path) -> None:
        self.stop(announce=False)
        self._stop = threading.Event()
        self._guard = SessionGuard(config.cooldown_seconds)
        if self.paused:
            self._guard.pause()
        self._thread = threading.Thread(
            target=self._run,
            args=(config, models_dir),
            name="xvoice-listen",
            daemon=True,
        )
        self._thread.start()

    def stop(self, announce: bool = True) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)
        self._thread = None
        if announce and self.state != "idle":
            self._emit("idle", "Stopped. The microphone is released.")

    def pause(self) -> None:
        self.paused = True
        if self._guard is not None:
            self._guard.pause()
        self._emit("paused", "Paused. The microphone is released.")

    def resume(self) -> None:
        self.paused = False
        if self._guard is not None:
            self._guard.resume()
        self._emit("listening", "Listening.")

    def run_blocking(self, config: Config, models_dir: Path, stop: threading.Event | None = None) -> int:
        """Listen until stop is set. The console uses this on the main thread."""
        self._stop = stop or threading.Event()
        self._guard = SessionGuard(config.cooldown_seconds)
        if self.paused:
            self._guard.pause()
        return self._run(config, models_dir)

    def _emit(self, state: str, detail: str) -> None:
        if state == self.state and detail == self.detail:
            return
        self.state = state
        self.detail = detail
        if detail:
            logging.info("%s", detail)
        if self._on_status is not None:
            try:
                self._on_status(state, detail)
            except Exception:
                logging.exception("Status update failed.")

    def _run(self, config: Config, models_dir: Path) -> int:
        phrase = spoken_phrase(config.wake_model)
        self._emit("loading", f'Loading the wake phrase "{phrase}".')
        try:
            paths = resolve_model_paths(
                models_dir, config.wake_model, extra_dirs=[user_models_dir()]
            )
            raw_model = load_wake_model(paths)
        except Exception as exc:
            self._emit(
                "error",
                "The wake-word files in this copy of x-voice could not be loaded. "
                f"Details: {exc}",
            )
            return 2
        listener = WakeListener(
            OpenWakeWordScorer(raw_model),
            config.threshold,
            trigger_frames=config.trigger_frames,
        )
        guard = self._guard or SessionGuard(config.cooldown_seconds)
        self._guard = guard
        self._emit("listening", f'Listening for "{phrase}".')
        while not self._stop.is_set():
            now = time.monotonic()
            guard.advance(now)
            if self.paused or guard.paused:
                self._emit("paused", "Paused. The microphone is released.")
                if self._stop.wait(0.2):
                    break
                continue
            if guard.phase is Phase.IN_CALL:
                self._poll_call(guard)
                continue
            if guard.phase is Phase.COOLDOWN:
                remaining = max(0.0, guard.cooldown_until - time.monotonic())
                self._emit("cooldown", f"Waiting {remaining:.0f} seconds before listening again.")
                if self._stop.wait(min(0.5, remaining or 0.2)):
                    break
                continue
            try:
                status = self._listen(config, listener, guard)
            except MicError as exc:
                self._emit("permission", f"{MIC_BLOCKED_MESSAGE} Details: {exc}")
                return 1
            if status == "accepted":
                try:
                    play_chime(config.chime)
                except Exception:
                    logging.exception("The chime did not play.")
                self._handle_trigger(config, guard)
            elif status == "paused":
                continue
            else:
                break
        self._emit("idle", "Stopped. The microphone is released.")
        return 0

    def _listen(self, config: Config, listener: WakeListener, guard: SessionGuard) -> str:
        listener.reset()
        try:
            devices = query_input_devices()
            chosen, notice = resolve_or_default(config.mic_device, devices)
        except MicError as exc:
            raise MicError(str(exc)) from exc
        if notice:
            self._emit("listening", notice)
        silence_checked = False
        warmup: list[bytes] = []
        with Microphone(chosen) as mic:
            self._emit("listening", "Microphone is open.")
            while not self._stop.is_set():
                if self.paused or guard.paused:
                    self._emit("paused", "Paused. The microphone is released.")
                    return "paused"
                frame = mic.read_frame()
                if not silence_checked:
                    warmup.append(frame)
                    if len(warmup) >= 8:
                        silence_checked = True
                        if is_blocked_silence(warmup):
                            self._emit("permission", SILENCE_MESSAGE)
                        warmup.clear()
                now = time.monotonic()
                score, ready = listener.observe(frame)
                if not ready:
                    continue
                allowed, reason = guard.allow_trigger(now)
                if not allowed:
                    logging.info("Wake phrase ignored (%s).", reason)
                    continue
                guard.begin_attempt(now)
                self._emit("triggered", f"Wake phrase accepted (score {score:.3f}). The microphone is released.")
                return "accepted"
        return "stopped"

    def _handle_trigger(self, config: Config, guard: SessionGuard) -> None:
        try:
            open_prompt_link(config.bot_id)
        except DeepLinkError as exc:
            self._emit("error", str(exc))
            guard.mark_failed(time.monotonic())
            return
        except OSError as exc:
            self._emit(
                "error",
                "Could not open the Grok Bot link. Install Grok Bot and sign in, then try again. "
                f"Details: {exc}",
            )
            guard.mark_failed(time.monotonic())
            return

        self._emit("launching", "Opened the voice bot chat.")
        window = wait_for_grok_window()
        if window is None:
            self._emit("error", "Grok Bot window was not found. Nothing was clicked.")
            guard.mark_failed(time.monotonic())
            return

        result = start_voice_chat(window)
        now = time.monotonic()
        if result.value == "clicked":
            guard.mark_clicked(now)
            self._emit("in_call", "Voice chat started. Listening stays off until the call ends.")
            return
        if result.value == "call_active":
            guard.mark_clicked(now)
            guard.mark_call_visible()
            self._emit("in_call", "A voice chat is already active. Nothing was clicked.")
            return
        if result.value == "draft_present":
            self._emit(
                "error",
                "Grok Bot's message box has other text, so x-voice could not confirm it was on "
                "the voice bot. Nothing was clicked and the text was left as it is. Clear it, "
                "then say the wake phrase again.",
            )
        elif result.value == "wrong_chat":
            self._emit(
                "error",
                "Grok Bot did not switch to the voice bot in time, so nothing was clicked. "
                "Check the bot id, then say the wake phrase again.",
            )
        elif result.value == "marker_stuck":
            self._emit(
                "error",
                'The voice bot is showing, but x-voice could not remove the word "x-voice" '
                "from its message box, so nothing was clicked. Delete it, then try again.",
            )
        else:
            self._emit("error", f"Did not start a voice chat ({result.value}).")
        guard.mark_failed(now)

    def _poll_call(self, guard: SessionGuard) -> None:
        self._emit("in_call", "Staying quiet while the voice chat is active.")
        while not self._stop.is_set() and guard.phase is Phase.IN_CALL and not guard.paused and not self.paused:
            window = _find_grok_quietly()
            now = time.monotonic()
            if window is None:
                guard.observe_call_ui(now, None)
            else:
                guard.observe_call_ui(now, call_ui_visible(window))
            if guard.phase is not Phase.IN_CALL or guard.paused or self.paused or self._stop.is_set():
                break
            self._stop.wait(0.5)


def _find_grok_quietly():
    try:
        from xvoice.automator import find_grok_window

        return find_grok_window()
    except Exception:
        logging.info("Could not look at the Grok Bot window.")
        return None
