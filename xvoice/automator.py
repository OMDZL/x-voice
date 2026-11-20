"""Find the Grok Bot window, confirm the voice bot is showing, and start the call.

pywinauto is imported inside the functions so this module can be imported
on Linux, where the unit tests run. Every action is limited to a window
whose process is Grok Bot. Buttons are invoked through UI Automation. There
is no coordinate click and no image match.

The prompt link puts the marker word (deeplink.MARKER_TEXT) into the voice
bot's message box, sometimes after a confirmation dialog. The sequence is:

1. If the link's dialog is showing and it carries the marker, press Confirm.
2. Wait until the message box holds exactly the marker. That proves the voice
   bot's chat is on screen. Without it, nothing is clicked.
3. Remove the marker: first through UI Automation's value setter, and only if
   that is not supported, by selecting and deleting it while the box is
   focused. Both happen only while the box holds exactly the marker, so text
   the owner typed is never removed.
4. Press Start voice chat.
"""

import ctypes
import logging
import os
import time
from enum import Enum

from xvoice.deeplink import MARKER_TEXT
from xvoice.windowmatch import (
    CONFIRM_BUTTON_NAME,
    ComposerCandidate,
    WindowCandidate,
    composer_has_draft,
    is_link_dialog,
    is_marker_only,
    is_start_button_name,
    matching_call_label,
    pick_composer_index,
    select_grok_window,
)

LAUNCH_WAIT_SECONDS = 12.0
POLL_SECONDS = 0.4
# Grok Bot can take a moment to switch to the bot's chat after the link opens.
BUTTON_WAIT_SECONDS = 6.0
MARKER_WAIT_SECONDS = 10.0


class ClickResult(Enum):
    CLICKED = "clicked"
    CALL_ACTIVE = "call_active"
    BUTTON_MISSING = "button_missing"
    WINDOW_MISSING = "window_missing"
    NOT_FOCUSED = "not_focused"
    DRAFT_PRESENT = "draft_present"
    WRONG_CHAT = "wrong_chat"
    MARKER_STUCK = "marker_stuck"


def find_grok_window():
    """Return the main Grok Bot UIA wrapper, or None."""
    candidates, wrappers = _top_level_windows()
    chosen = select_grok_window(candidates)
    if chosen is None:
        return None
    wrapper = wrappers.get(chosen.hwnd)
    if wrapper is None:
        return None
    process_name = _process_basename(int(wrapper.process_id()))
    if process_name.casefold() not in {"grok bot.exe", "grokbot.exe"}:
        logging.error("Refusing a window whose process is %s.", process_name or "unknown")
        return None
    return wrapper


def wait_for_grok_window(timeout_seconds: float = LAUNCH_WAIT_SECONDS):
    """Poll for the Grok Bot window after the deep link is opened."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        window = find_grok_window()
        if window is not None:
            return window
        if time.monotonic() >= deadline:
            return None
        time.sleep(POLL_SECONDS)


def call_ui_visible(window) -> bool | None:
    """True when an in-call label is showing, False when the window has none.

    None means the window's controls could not be read.
    """
    try:
        names = _descendant_names(window)
    except Exception:
        logging.exception("Could not read controls in the Grok Bot window.")
        return None
    return matching_call_label(names) is not None


def start_voice_chat(window) -> ClickResult:
    """Confirm the voice bot is showing, remove the marker, and start the call."""
    try:
        return _start_voice_chat(window)
    except Exception:
        logging.exception("Grok Bot automation stopped. Nothing else was clicked.")
        return ClickResult.BUTTON_MISSING


def _start_voice_chat(window) -> ClickResult:
    pid = int(window.process_id())
    if not _focus_grok(window, pid):
        logging.error(
            "Grok Bot did not come to the foreground. No keys were sent and the button was not clicked."
        )
        return ClickResult.NOT_FOCUSED

    label = matching_call_label(_descendant_names(window))
    if label is not None:
        logging.info("A voice chat is already active (%s). No button was clicked.", label)
        return ClickResult.CALL_ACTIVE

    composer, outcome = _wait_for_marker(window)
    if composer is None:
        return outcome

    if not _remove_marker(composer, pid):
        return ClickResult.MARKER_STUCK

    button = _find_start_button(window)
    if button is not None:
        return _invoke_start(button)
    logging.error(
        "The voice bot's chat is showing, but Start voice chat was not found. Nothing was clicked. "
        "Buttons in the Grok Bot window: %s",
        ", ".join(_button_names(window)) or "none could be read",
    )
    return ClickResult.BUTTON_MISSING


def _wait_for_marker(window, wait_seconds: float | None = None):
    """Return (message box, None) once it holds exactly the marker, or (None, result).

    The link's confirmation dialog is answered here when it shows the marker.
    """
    if wait_seconds is None:
        wait_seconds = MARKER_WAIT_SECONDS
    deadline = time.monotonic() + wait_seconds
    saw_other_text = False
    confirmed = False
    while True:
        try:
            elements = list(window.descendants())
        except Exception as exc:
            logging.info("Could not read the Grok Bot window: %s", exc)
            elements = []
        names = [_safe_name(element) for element in elements]
        if is_link_dialog(names):
            if not confirmed and _confirm_link_dialog(elements):
                confirmed = True
            # Do not read the message box while the dialog is up: its field
            # also shows the marker.
        else:
            composer = _pick_composer(window)
            value = _read_composer_value(composer) if composer is not None else None
            if is_marker_only(value, MARKER_TEXT):
                logging.info("The voice bot's chat is showing.")
                return composer, None
            saw_other_text = composer_has_draft(value)
        if time.monotonic() >= deadline:
            break
        time.sleep(POLL_SECONDS)

    if saw_other_text:
        logging.error(
            "The Grok Bot message box has other text, so x-voice cannot tell that the voice "
            "bot's chat is showing. The text was left as it is and nothing was clicked."
        )
        return None, ClickResult.DRAFT_PRESENT
    logging.error(
        "The voice bot's chat did not appear (the marker never reached the message box). "
        "Nothing was clicked. Buttons in the Grok Bot window: %s",
        ", ".join(_button_names(window)) or "none could be read",
    )
    return None, ClickResult.WRONG_CHAT


def _confirm_link_dialog(elements) -> bool:
    """Press Confirm on Grok Bot's link dialog, only when it shows the marker."""
    shows_marker = any(
        _safe_name(element).strip() == MARKER_TEXT
        or is_marker_only(_read_composer_value(element), MARKER_TEXT)
        for element in elements
    )
    if not shows_marker:
        logging.error(
            "A Grok Bot link dialog is open, but it does not show x-voice's text. "
            "It was left for you to answer."
        )
        return False
    for element in elements:
        if _safe_name(element).strip() == CONFIRM_BUTTON_NAME and _control_type(element) == "Button":
            try:
                element.invoke()
            except Exception as exc:
                logging.error("Could not press Confirm on the Grok Bot link dialog: %s", exc)
                return False
            logging.info("Confirmed Grok Bot's link dialog for x-voice's text.")
            return True
    logging.error("The Grok Bot link dialog has no Confirm button that x-voice can press.")
    return False


def _remove_marker(composer, pid: int) -> bool:
    """Empty the message box while it holds only the marker. Never touches other text."""
    if not is_marker_only(_read_composer_value(composer), MARKER_TEXT):
        logging.error("The message box changed before x-voice could clear its text. Nothing was clicked.")
        return False
    try:
        composer.iface_value.SetValue("")
    except Exception as exc:
        logging.info("Grok Bot's message box does not accept a direct clear (%s).", exc)
    time.sleep(0.2)
    if not composer_has_draft(_read_composer_value(composer)):
        logging.info("Removed x-voice's text from the message box.")
        return True

    # Fallback: select and delete, only with that box focused and still
    # holding exactly the marker.
    try:
        composer.set_focus()
    except Exception:
        logging.error("Could not focus the message box. No keys were sent.")
        return False
    time.sleep(0.2)
    if _foreground_pid() != pid or not _focus_is_element(composer, pid):
        logging.error("The message box is not the focused control. No keys were sent.")
        return False
    if not is_marker_only(_read_composer_value(composer), MARKER_TEXT):
        logging.error("The message box changed before x-voice could clear its text. No keys were sent.")
        return False
    try:
        composer.type_keys("^a{DELETE}", set_foreground=False, pause=0.05)
    except Exception:
        logging.exception("Could not clear x-voice's text. No further keys were sent.")
        return False
    time.sleep(0.2)
    if composer_has_draft(_read_composer_value(composer)):
        logging.error("x-voice's text is still in the message box. Nothing was clicked.")
        return False
    logging.info("Removed x-voice's text from the message box.")
    return True


def _focus_is_element(element, pid: int) -> bool:
    try:
        from pywinauto import Desktop

        focused = Desktop(backend="uia").get_focus()
    except Exception:
        return False
    if focused is None:
        return False
    try:
        if int(focused.element_info.process_id) != pid:
            return False
        return tuple(focused.element_info.runtime_id) == tuple(element.element_info.runtime_id)
    except Exception:
        return False


def _control_type(element) -> str:
    try:
        return str(element.element_info.control_type)
    except Exception:
        return ""


def _button_names(window, limit: int = 40) -> list[str]:
    """Names of buttons in the Grok Bot window, to diagnose a renamed button."""
    names: list[str] = []
    try:
        for element in window.descendants(control_type="Button"):
            name = _safe_name(element).strip()
            if name and name not in names:
                names.append(name)
            if len(names) >= limit:
                break
    except Exception:
        return names
    return names


def _focus_grok(window, pid: int) -> bool:
    try:
        if window.is_minimized():
            window.restore()
    except Exception:
        logging.info("Could not restore the Grok Bot window. Trying to focus it anyway.")
    try:
        window.set_focus()
    except Exception:
        logging.info("The first attempt to focus Grok Bot failed.")
    time.sleep(0.3)
    if _foreground_pid() == pid:
        return True
    try:
        window.set_focus()
    except Exception:
        return False
    time.sleep(0.3)
    return _foreground_pid() == pid


def _find_start_button(window, wait_seconds: float | None = None):
    """Return the Start voice chat button, polling while Grok Bot opens the chat.

    The window object is a UI Automation wrapper, so the search uses its
    descendants. Only a Button whose name is Start voice chat is returned.
    """
    if wait_seconds is None:
        wait_seconds = BUTTON_WAIT_SECONDS
    deadline = time.monotonic() + wait_seconds
    reported = False
    while True:
        try:
            for element in window.descendants(control_type="Button"):
                if is_start_button_name(_safe_name(element)):
                    return element
        except Exception as exc:
            if not reported:
                logging.info("Looking for Start voice chat raised an error: %s", exc)
                reported = True
        if time.monotonic() >= deadline:
            return None
        time.sleep(POLL_SECONDS)


def _invoke_start(button) -> ClickResult:
    try:
        # InvokePattern clicks this element only. It does not move the mouse
        # and it does not send keys to the foreground window.
        button.invoke()
    except Exception:
        logging.exception("Could not invoke Start voice chat. Nothing else was clicked.")
        return ClickResult.BUTTON_MISSING
    logging.info("Clicked Start voice chat.")
    return ClickResult.CLICKED


def _pick_composer(window):
    # Only text boxes. The page itself is a Document whose value is not a draft.
    try:
        elements = list(window.descendants(control_type="Edit"))
    except Exception:
        return None
    candidates: list[ComposerCandidate] = []
    for element in elements:
        name = _safe_name(element)
        width, height = _element_size(element)
        candidates.append(
            ComposerCandidate(
                name=name,
                width=width,
                height=height,
                value=_read_composer_value(element),
            )
        )
    index = pick_composer_index(candidates)
    if index is None:
        return None
    return elements[index]


def _read_composer_value(element) -> str | None:
    try:
        return str(element.get_value())
    except Exception:
        pass
    try:
        return str(element.iface_value.CurrentValue)
    except Exception:
        return None


def _top_level_windows():
    from pywinauto import Desktop

    desktop = Desktop(backend="uia")
    candidates: list[WindowCandidate] = []
    wrappers: dict[int, object] = {}
    for wrapper in desktop.windows():
        try:
            hwnd = int(wrapper.handle)
            rect = wrapper.rectangle()
            pid = int(wrapper.process_id())
            candidates.append(
                WindowCandidate(
                    pid=pid,
                    process_name=_process_basename(pid),
                    title=wrapper.window_text() or "",
                    width=int(rect.width()),
                    height=int(rect.height()),
                    hwnd=hwnd,
                )
            )
            wrappers[hwnd] = wrapper
        except Exception:
            continue
    return candidates, wrappers


def _descendant_names(window) -> list[str]:
    names: list[str] = []
    for element in window.descendants():
        try:
            text = element.window_text() or ""
        except Exception:
            continue
        if text:
            names.append(text)
    return names


def _safe_name(element) -> str:
    try:
        return element.window_text() or ""
    except Exception:
        return ""


def _element_size(element) -> tuple[int, int]:
    try:
        rect = element.rectangle()
        return max(0, int(rect.width())), max(0, int(rect.height()))
    except Exception:
        return 0, 0


def _foreground_pid() -> int:
    user32 = ctypes.windll.user32
    hwnd = int(user32.GetForegroundWindow())
    if not hwnd:
        return 0
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _process_basename(pid: int) -> str:
    if pid <= 0:
        return ""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    access = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
    handle = kernel32.OpenProcess(access, False, pid)
    if not handle:
        return ""
    try:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
        if not ok:
            return ""
        return os.path.basename(buffer.value)
    finally:
        kernel32.CloseHandle(handle)
