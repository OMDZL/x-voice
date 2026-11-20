"""Cooldown and active-call guard.

A wake phrase is ignored while the user has paused, while a call is in
progress, or while the cooldown after a trigger has not elapsed.

Call detection is preferred: once the Grok Bot window shows an in-call
label, listening stays off until that label is gone. If the call screen
cannot be seen, listening stays off until cooldown_seconds has passed.
A failed attempt uses the same cooldown so a noisy room cannot hammer the UI.
After a call ends, the cooldown runs once more before listening can fire.
"""

from dataclasses import dataclass
from enum import Enum


class Phase(Enum):
    LISTENING = "listening"
    IN_CALL = "in_call"
    COOLDOWN = "cooldown"


@dataclass
class SessionGuard:
    cooldown_seconds: float
    phase: Phase = Phase.LISTENING
    paused: bool = False
    cooldown_until: float = 0.0
    saw_call_ui: bool = False
    missing_since: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.cooldown_seconds, bool) or not isinstance(
            self.cooldown_seconds, (int, float)
        ):
            raise ValueError("cooldown_seconds must be a number of seconds.")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be zero or greater.")

    def allow_trigger(self, now: float) -> tuple[bool, str]:
        """Return whether a wake phrase at time `now` may start a call."""
        self.advance(now)
        if self.paused:
            return False, "paused"
        if self.phase is Phase.IN_CALL:
            return False, "call_active"
        if self.phase is Phase.COOLDOWN:
            return False, "cooldown"
        return True, "ok"

    def advance(self, now: float) -> None:
        """Move from cooldown back to listening once the wait has elapsed."""
        if self.phase is Phase.COOLDOWN and now >= self.cooldown_until:
            self.phase = Phase.LISTENING

    def pause(self) -> None:
        """Stop listening and release the microphone. An in-call wait is kept."""
        self.paused = True

    def resume(self) -> None:
        """Allow listening again. Does not cancel an active call guard."""
        self.paused = False

    def begin_attempt(self, now: float) -> None:
        """Hold off further triggers while this one opens Grok Bot."""
        self.phase = Phase.IN_CALL
        self.saw_call_ui = False
        self.missing_since = None
        self.cooldown_until = now + self.cooldown_seconds

    def mark_clicked(self, now: float) -> None:
        """A click landed, or a call was already up. Keep the microphone free."""
        self.phase = Phase.IN_CALL
        self.missing_since = None
        self.cooldown_until = now + self.cooldown_seconds

    def mark_call_visible(self) -> None:
        """The Grok Bot window is showing an in-call control."""
        self.phase = Phase.IN_CALL
        self.saw_call_ui = True
        self.missing_since = None

    def mark_failed(self, now: float) -> None:
        """The attempt did not start a call. Wait, then listen again."""
        self._enter_cooldown(now)

    def observe_call_ui(self, now: float, visible: bool | None) -> None:
        """Update the in-call wait from one look at the Grok Bot window.

        visible True: an in-call label is showing.
        visible False: the Grok Bot window is there and those labels are not.
        visible None: the Grok Bot window could not be read.
        """
        if self.phase is not Phase.IN_CALL:
            return
        if visible is True:
            self.saw_call_ui = True
            self.missing_since = None
            return
        if visible is False:
            self.missing_since = None
            if self.saw_call_ui:
                self._enter_cooldown(now)
            elif now >= self.cooldown_until:
                self.phase = Phase.LISTENING
            return
        # The window could not be read.
        if not self.saw_call_ui:
            if now >= self.cooldown_until:
                self.phase = Phase.LISTENING
            return
        if self.missing_since is None:
            self.missing_since = now
        if now >= self.missing_since + self.cooldown_seconds:
            self.phase = Phase.LISTENING
            self.saw_call_ui = False
            self.missing_since = None

    def _enter_cooldown(self, now: float) -> None:
        self.saw_call_ui = False
        self.missing_since = None
        self.cooldown_until = now + self.cooldown_seconds
        if self.cooldown_seconds > 0:
            self.phase = Phase.COOLDOWN
        else:
            self.phase = Phase.LISTENING
