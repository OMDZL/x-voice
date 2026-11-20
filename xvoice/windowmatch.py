"""Decide which window is Grok Bot, without touching any window.

The running app only automates a top-level window whose process is
Grok Bot. These helpers are the rules for that choice. They are pure
so they can be tested off Windows.
"""

from dataclasses import dataclass

# Process image names for the Grok Bot desktop app. Bare "Grok" is rejected
# so a browser tab or another product is never selected.
GROK_PROCESS_NAMES = frozenset({"grok bot.exe", "grokbot.exe"})

# Skip the small Grok Bot strips (for example a 240x30 slice) and use the
# main window.
MIN_WINDOW_WIDTH = 400
MIN_WINDOW_HEIGHT = 300

START_BUTTON_NAME = "Start voice chat"

# Grok Bot's confirmation for a prompt link: "Add Message for <bot>?" with
# Cancel and Confirm. x-voice presses Confirm only when the dialog shows its
# own marker word. It never touches "Don't show again".
LINK_DIALOG_PREFIX = "add message for"
CONFIRM_BUTTON_NAME = "Confirm"
CANCEL_BUTTON_NAME = "Cancel"

# Labels documented for an in-progress desktop voice chat, plus the prompt
# shown when a second call would end the current one. Matching is exact.
CALL_ACTIVE_NAMES = frozenset(
    {
        "Hang up",
        "End the current voice chat?",
        "Voice chat in progress",
        "Return to the voice chat",
    }
)

COMPOSER_NAME_HINTS = ("message", "prompt", "composer", "ask")


@dataclass(frozen=True)
class WindowCandidate:
    pid: int
    process_name: str
    title: str
    width: int
    height: int
    hwnd: int


@dataclass(frozen=True)
class ComposerCandidate:
    name: str
    width: int
    height: int
    value: str | None


def is_grok_process(process_name: str) -> bool:
    return process_name.strip().casefold() in GROK_PROCESS_NAMES


def select_grok_window(candidates: list[WindowCandidate]) -> WindowCandidate | None:
    """Pick the main Grok Bot window, or None when there is no safe choice."""
    owned = [
        candidate
        for candidate in candidates
        if is_grok_process(candidate.process_name)
        and candidate.width >= MIN_WINDOW_WIDTH
        and candidate.height >= MIN_WINDOW_HEIGHT
    ]
    if not owned:
        return None
    titled = [candidate for candidate in owned if "Grok Bot" in candidate.title]
    pool = titled or owned
    return max(pool, key=lambda candidate: candidate.width * candidate.height)


def is_start_button_name(name: str) -> bool:
    """True when a button's accessible name is Start voice chat."""
    return (name or "").strip().casefold() == START_BUTTON_NAME.casefold()


def is_marker_only(text: str | None, marker: str) -> bool:
    """True when the message box holds the marker word and nothing else."""
    if text is None:
        return False
    return text.strip() == marker


def is_link_dialog(names: list[str]) -> bool:
    """True when the visible names look like Grok Bot's link confirmation.

    Either the "Add Message for ...?" title is present, or Confirm and
    Cancel buttons appear together.
    """
    folded = [(name or "").strip().casefold() for name in names]
    if any(name.startswith(LINK_DIALOG_PREFIX) for name in folded):
        return True
    return CONFIRM_BUTTON_NAME.casefold() in folded and CANCEL_BUTTON_NAME.casefold() in folded


def matching_call_label(names: list[str]) -> str | None:
    """Return the in-call label when one of the names matches exactly."""
    wanted = {name.casefold(): name for name in CALL_ACTIVE_NAMES}
    for name in names:
        key = (name or "").strip().casefold()
        if key in wanted:
            return wanted[key]
    return None


def composer_has_draft(text: str | None) -> bool:
    """True only when the composer value is non-empty text.

    None means the value could not be read, which is not treated as a draft.
    """
    if text is None:
        return False
    return text.strip() != ""


def pick_composer_index(candidates: list[ComposerCandidate]) -> int | None:
    """Choose the message composer among edit controls in the Grok Bot window.

    Search boxes are skipped. A control whose name looks like a message box
    wins over other edits. Among the remaining controls, the largest one is
    the composer.
    """
    pool: list[tuple[int, ComposerCandidate]] = []
    for index, candidate in enumerate(candidates):
        if "search" in candidate.name.casefold():
            continue
        pool.append((index, candidate))
    if not pool:
        return None
    hinted = [
        item
        for item in pool
        if any(hint in item[1].name.casefold() for hint in COMPOSER_NAME_HINTS)
    ]
    use = hinted or pool
    best = max(use, key=lambda item: item[1].width * item[1].height)
    return best[0]
