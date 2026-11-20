"""The call starts only once the voice bot's chat is proven to be on screen.

The fake window mirrors a pywinauto UIA wrapper: it has descendants(), not
child_window(). The link puts the marker word in the voice bot's message box,
sometimes after an "Add Message for ...?" dialog.
"""

from pathlib import Path

import pytest

from xvoice import automator
from xvoice.automator import ClickResult
from xvoice.deeplink import MARKER_TEXT


class _Info:
    def __init__(self, control_type: str) -> None:
        self.control_type = control_type
        self.process_id = 1234
        self.runtime_id = (id(self),)


class _Element:
    def __init__(self, name: str, control_type: str) -> None:
        self.name = name
        self.element_info = _Info(control_type)
        self.invoked = 0
        self.on_invoke = None

    def window_text(self) -> str:
        return self.name

    def rectangle(self):
        raise RuntimeError("no size")

    def invoke(self) -> None:
        self.invoked += 1
        if self.on_invoke is not None:
            self.on_invoke()


class _ValueIface:
    def __init__(self, box: "_Composer") -> None:
        self.box = box

    @property
    def CurrentValue(self) -> str:  # noqa: N802 - UIA property name
        return self.box.value

    def SetValue(self, value: str) -> None:  # noqa: N802 - UIA method name
        if not self.box.set_value_supported:
            raise RuntimeError("ValuePattern is read-only")
        self.box.value = value


class _Composer(_Element):
    def __init__(self, value: str = "", set_value_supported: bool = True) -> None:
        super().__init__("Message", "Edit")
        self.value = value
        self.set_value_supported = set_value_supported
        self.keys_sent: list[str] = []
        self.iface_value = _ValueIface(self)

    def set_focus(self) -> None:
        pass

    def type_keys(self, keys, **_kwargs) -> None:
        self.keys_sent.append(keys)
        if keys == "^a{DELETE}":
            self.value = ""


class _FakeGrok:
    def __init__(
        self,
        composer: _Composer,
        dialog: bool = False,
        dialog_text: str = MARKER_TEXT,
        marker_after: int | None = 1,
        old_chat_has_start_button: bool = False,
    ) -> None:
        self.composer = composer
        self.dialog = dialog
        self.polls = 0
        self.marker_after = marker_after
        self.old_chat = old_chat_has_start_button
        self.start = _Element("Start voice chat", "Button")
        self.title = _Element("Add Message for Computer · X-Voice Assistant?", "Text")
        self.field = _Element(dialog_text, "Edit")
        self.confirm = _Element("Confirm", "Button")
        self.cancel = _Element("Cancel", "Button")
        self.dont_show = _Element("Don't show again", "CheckBox")
        self.confirm.on_invoke = self._confirmed
        self.settings = _Element("Settings", "Button")

    def _confirmed(self) -> None:
        self.dialog = False
        self.composer.value = MARKER_TEXT
        self._arrived = True

    def process_id(self) -> int:
        return 1234

    def _tick(self) -> None:
        self.polls += 1
        if not self.dialog and self.marker_after is not None and self.polls > self.marker_after:
            if self.composer.value == "" and not self.start.invoked and not self._arrived:
                self.composer.value = MARKER_TEXT
                self._arrived = True

    _arrived = False

    def _buttons(self) -> list[_Element]:
        buttons = [self.settings]
        if self.dialog:
            buttons += [self.confirm, self.cancel]
        # Grok Bot shows Start voice chat only while the message box is empty.
        if self.composer.value == "" and (self._arrived or self.old_chat):
            buttons.append(self.start)
        return buttons

    def descendants(self, control_type=None):
        if control_type is None:
            self._tick()
            items = [self.composer, *self._buttons()]
            if self.dialog:
                items += [self.title, self.field, self.dont_show]
            return items
        if control_type == "Button":
            return self._buttons()
        if control_type == "Edit":
            return [self.composer] + ([self.field] if self.dialog else [])
        return []


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(automator, "_focus_grok", lambda window, pid: True)
    monkeypatch.setattr(automator, "_foreground_pid", lambda: 1234)
    monkeypatch.setattr(automator, "_focus_is_element", lambda element, pid: True)
    monkeypatch.setattr(automator, "POLL_SECONDS", 0)
    monkeypatch.setattr(automator, "MARKER_WAIT_SECONDS", 0.3)
    monkeypatch.setattr(automator, "BUTTON_WAIT_SECONDS", 0.2)
    monkeypatch.setattr(automator.time, "sleep", lambda _seconds: None)


def test_marker_arrives_then_it_is_cleared_and_the_call_starts(fast):
    box = _Composer()
    grok = _FakeGrok(box, marker_after=2)
    assert automator.start_voice_chat(grok) is ClickResult.CLICKED
    assert grok.start.invoked == 1
    assert box.value == ""
    assert box.keys_sent == []  # cleared without any keystroke


def test_link_dialog_is_confirmed_and_dont_show_again_is_never_touched(fast):
    box = _Composer()
    grok = _FakeGrok(box, dialog=True, marker_after=None)
    assert automator.start_voice_chat(grok) is ClickResult.CLICKED
    assert grok.confirm.invoked == 1
    assert grok.cancel.invoked == 0
    assert grok.dont_show.invoked == 0
    assert grok.start.invoked == 1


def test_dialog_with_someone_elses_text_is_left_alone(fast):
    box = _Composer()
    grok = _FakeGrok(box, dialog=True, dialog_text="hello", marker_after=None)
    assert automator.start_voice_chat(grok) is ClickResult.WRONG_CHAT
    assert grok.confirm.invoked == 0
    assert grok.start.invoked == 0


def test_other_bot_chat_with_a_voice_button_is_never_clicked(fast):
    """The link did nothing, and the bot already on screen has a voice button."""
    box = _Composer()
    grok = _FakeGrok(box, marker_after=None, old_chat_has_start_button=True)
    assert automator.start_voice_chat(grok) is ClickResult.WRONG_CHAT
    assert grok.start.invoked == 0


def test_owner_draft_is_never_cleared(fast):
    for draft in ("my half-written message", f"my draft {MARKER_TEXT}"):
        box = _Composer(value=draft)
        grok = _FakeGrok(box, marker_after=None)
        assert automator.start_voice_chat(grok) is ClickResult.DRAFT_PRESENT
        assert box.value == draft
        assert box.keys_sent == []
        assert grok.start.invoked == 0


def test_keystroke_fallback_only_when_value_setter_is_read_only(fast):
    box = _Composer(set_value_supported=False)
    grok = _FakeGrok(box, marker_after=1)
    assert automator.start_voice_chat(grok) is ClickResult.CLICKED
    assert box.keys_sent == ["^a{DELETE}"]
    assert grok.start.invoked == 1


def test_no_keys_when_the_box_is_not_focused(fast, monkeypatch):
    monkeypatch.setattr(automator, "_focus_is_element", lambda element, pid: False)
    box = _Composer(set_value_supported=False)
    grok = _FakeGrok(box, marker_after=1)
    assert automator.start_voice_chat(grok) is ClickResult.MARKER_STUCK
    assert box.keys_sent == []
    assert grok.start.invoked == 0


def test_the_only_keystrokes_in_the_automator_are_select_and_delete():
    source = Path(automator.__file__).read_text(encoding="utf-8")
    assert source.count("type_keys(") == 1
    assert 'type_keys("^a{DELETE}"' in source
    assert "send_keys" not in source


def test_link_dialog_and_marker_rules():
    from xvoice.windowmatch import is_link_dialog, is_marker_only

    assert is_link_dialog(["Add Message for Computer · X-Voice Assistant?"])
    assert is_link_dialog(["Confirm", "Cancel"])
    assert not is_link_dialog(["Confirm"])
    assert not is_link_dialog(["Start voice chat", "Settings"])
    assert is_marker_only(f" {MARKER_TEXT} ", MARKER_TEXT)
    assert not is_marker_only(f"hi {MARKER_TEXT}", MARKER_TEXT)
    assert not is_marker_only(None, MARKER_TEXT)
