"""Cooldown and the active-call guard."""

import pytest

from xvoice.guard import Phase, SessionGuard


def test_trigger_is_allowed_when_listening():
    guard = SessionGuard(10)
    allowed, reason = guard.allow_trigger(0)
    assert allowed is True
    assert reason == "ok"


def test_failed_attempt_uses_the_cooldown():
    guard = SessionGuard(5)
    guard.mark_failed(0)
    assert guard.phase is Phase.COOLDOWN
    assert guard.allow_trigger(4.9) == (False, "cooldown")
    allowed, reason = guard.allow_trigger(5)
    assert allowed is True
    assert reason == "ok"
    assert guard.phase is Phase.LISTENING


def test_zero_cooldown_listens_again_immediately():
    guard = SessionGuard(0)
    guard.mark_failed(3)
    assert guard.phase is Phase.LISTENING
    assert guard.allow_trigger(3) == (True, "ok")


def test_begin_attempt_blocks_until_the_call_fallback_elapses():
    guard = SessionGuard(10)
    guard.begin_attempt(0)
    assert guard.allow_trigger(1) == (False, "call_active")
    # The window is visible but the in-call labels are not. Wait out the fallback.
    guard.observe_call_ui(1, False)
    assert guard.phase is Phase.IN_CALL
    guard.observe_call_ui(10, False)
    assert guard.phase is Phase.LISTENING
    assert guard.allow_trigger(10) == (True, "ok")


def test_visible_call_outlasts_the_cooldown_and_then_waits_again():
    guard = SessionGuard(10)
    guard.begin_attempt(0)
    guard.mark_call_visible()
    guard.observe_call_ui(50, True)
    assert guard.phase is Phase.IN_CALL
    assert guard.allow_trigger(50) == (False, "call_active")
    guard.observe_call_ui(51, False)
    assert guard.phase is Phase.COOLDOWN
    assert guard.allow_trigger(60) == (False, "cooldown")
    assert guard.allow_trigger(61) == (True, "ok")


def test_missing_window_after_a_seen_call_keeps_the_guard():
    guard = SessionGuard(10)
    guard.begin_attempt(0)
    guard.mark_call_visible()
    guard.observe_call_ui(5, None)
    assert guard.phase is Phase.IN_CALL
    guard.observe_call_ui(14, None)
    assert guard.phase is Phase.IN_CALL
    guard.observe_call_ui(15, None)
    assert guard.phase is Phase.LISTENING


def test_unseen_call_falls_back_when_the_window_cannot_be_read():
    guard = SessionGuard(8)
    guard.mark_clicked(0)
    guard.observe_call_ui(7, None)
    assert guard.phase is Phase.IN_CALL
    guard.observe_call_ui(8, None)
    assert guard.phase is Phase.LISTENING


def test_pause_blocks_and_does_not_clear_an_active_call():
    guard = SessionGuard(10)
    guard.begin_attempt(0)
    guard.pause()
    assert guard.allow_trigger(1) == (False, "paused")
    guard.resume()
    assert guard.allow_trigger(1) == (False, "call_active")
    guard.pause()
    guard.resume()
    assert guard.phase is Phase.IN_CALL


def test_negative_cooldown_is_rejected():
    with pytest.raises(ValueError):
        SessionGuard(-1)
