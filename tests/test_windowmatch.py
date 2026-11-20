"""Window and composer selection never chooses another app."""

from xvoice.windowmatch import (
    ComposerCandidate,
    WindowCandidate,
    composer_has_draft,
    matching_call_label,
    pick_composer_index,
    select_grok_window,
)


def _window(process: str, title: str, width: int, height: int, hwnd: int = 1, pid: int = 10) -> WindowCandidate:
    return WindowCandidate(pid, process, title, width, height, hwnd)


def test_only_the_grok_bot_process_is_selected():
    chrome = _window("chrome.exe", "Grok Bot", 1200, 800, hwnd=1)
    browser_tab = _window("msedge.exe", "ai-grok-bot", 1200, 800, hwnd=2)
    bare = _window("Grok.exe", "Grok", 1200, 800, hwnd=3)
    grok = _window("Grok Bot.exe", "Grok Bot", 1100, 700, hwnd=4)
    assert select_grok_window([chrome, browser_tab, bare, grok]) == grok


def test_tiny_grok_strip_is_ignored_and_largest_titled_window_wins():
    strip = _window("Grok Bot.exe", "Grok Bot", 240, 30, hwnd=1)
    small = _window("Grok Bot.exe", "Notes", 500, 400, hwnd=2)
    main = _window("Grok Bot.exe", "Voice - Grok Bot", 1400, 900, hwnd=3)
    other = _window("GrokBot.exe", "Grok Bot", 800, 600, hwnd=4)
    assert select_grok_window([strip, small, other, main]) == main


def test_untitled_main_window_is_used_when_no_title_matches():
    left = _window("Grok Bot.exe", "Chat", 600, 500, hwnd=1)
    right = _window("Grok Bot.exe", "Chat", 900, 700, hwnd=2)
    assert select_grok_window([left, right]) == right


def test_no_grok_window_returns_none():
    assert select_grok_window([_window("chrome.exe", "Grok Bot", 800, 600)]) is None


def test_call_labels_match_exactly():
    assert matching_call_label(["Hang up"]) == "Hang up"
    assert matching_call_label(["  end the current voice chat? "]) == "End the current voice chat?"
    assert matching_call_label(["Voice chat in progress"]) == "Voice chat in progress"
    assert matching_call_label(["End the current voice chat? Choose End"]) is None
    assert matching_call_label(["Start voice chat"]) is None


def test_composer_clear_only_when_text_is_present():
    assert composer_has_draft(None) is False
    assert composer_has_draft("") is False
    assert composer_has_draft("   ") is False
    assert composer_has_draft("hello") is True


def test_composer_picker_skips_search_and_prefers_the_message_box():
    candidates = [
        ComposerCandidate("Search", 400, 40, ""),
        ComposerCandidate("Notes", 900, 400, "leftover"),
        ComposerCandidate("Message", 700, 80, "draft"),
    ]
    assert pick_composer_index(candidates) == 2


def test_start_button_name_match_is_exact_but_ignores_case_and_spaces():
    from xvoice.windowmatch import is_start_button_name

    assert is_start_button_name("Start voice chat")
    assert is_start_button_name("  start Voice Chat ")
    assert not is_start_button_name("Start voice chat with Ani")
    assert not is_start_button_name("")
