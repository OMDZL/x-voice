"""The bot id cannot add parameters, and the opened link carries only the marker text."""

from urllib.parse import parse_qs, urlsplit

import pytest

from xvoice.deeplink import MARKER_TEXT, DeepLinkError, build_launch_link, build_prompt_link
from xvoice.launcher import open_prompt_link


def _query(link: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(link).query, keep_blank_values=True)


def test_link_is_id_only():
    link = build_prompt_link("voice-bot-1")
    assert link == "grokbot://app/v1/prompt?id=voice-bot-1"
    parts = urlsplit(link)
    assert parts.scheme == "grokbot"
    assert parts.path == "/v1/prompt"
    assert list(_query(link)) == ["id"]
    assert _query(link)["id"] == ["voice-bot-1"]
    assert "text" not in link.lower()
    assert "text=" not in link.lower()


def test_text_injection_is_rejected():
    for bot_id in ("abc&text=hello", "abc?text=hello", "abc#text", "hello world", "a/b"):
        with pytest.raises(DeepLinkError):
            build_prompt_link(bot_id)


def test_placeholder_and_empty_are_rejected():
    with pytest.raises(DeepLinkError, match="PASTE_BOT_ID_HERE"):
        build_prompt_link("PASTE_BOT_ID_HERE")
    with pytest.raises(DeepLinkError, match="empty"):
        build_prompt_link("  ")


def test_encoded_id_still_has_no_text_parameter():
    link = build_prompt_link("boté")
    assert list(_query(link)) == ["id"]
    assert _query(link)["id"] == ["boté"]
    assert "text" not in link.lower()


def test_open_does_not_run_off_windows(monkeypatch):
    """Opening must fail before any window is touched when this is not Windows."""
    monkeypatch.setattr("xvoice.launcher.sys.platform", "linux")
    with pytest.raises(DeepLinkError, match="Windows"):
        open_prompt_link("voice-bot-1")


def test_launch_link_carries_only_the_marker():
    link = build_launch_link("voice-bot-1")
    assert link == "grokbot://app/v1/prompt?id=voice-bot-1&text=x-voice"
    query = _query(link)
    assert list(query) == ["id", "text"]
    assert query["text"] == [MARKER_TEXT]


def test_launch_link_rejects_an_id_that_adds_text():
    for bot_id in ("abc&text=hello", "abc?text=hello", "abc#x", "a b"):
        with pytest.raises(DeepLinkError):
            build_launch_link(bot_id)
