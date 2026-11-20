"""Wake-word loop with fake frames and a mock model. No audio is written."""

from xvoice.detector import BUFFER_FRAMES, FRAME_SAMPLES, WakeListener, run_detection_loop
from xvoice.guard import SessionGuard


def _frame(marker: int = 0) -> bytes:
    return bytes((marker, 0)) * FRAME_SAMPLES


class ScriptedModel:
    def __init__(self, scores: list[float]) -> None:
        self.scores = list(scores)
        self.seen: list[bytes] = []

    def predict(self, frame: bytes) -> dict[str, float]:
        self.seen.append(frame)
        value = self.scores.pop(0) if self.scores else 0.0
        return {"hey_jarvis": value}


def test_loop_accepts_one_hit_and_guards_the_next():
    model = ScriptedModel([0.1, 0.9, 0.95])
    guard = SessionGuard(10)
    frames = [(0.0, _frame()), (1.0, _frame(1)), (2.0, _frame(2))]
    events = run_detection_loop(frames, model, threshold=0.5, guard=guard)
    assert [(event.kind, event.reason) for event in events] == [
        ("accepted", "ok"),
        ("ignored", "call_active"),
    ]
    assert events[0].score == 0.9
    assert model.seen == [_frame(), _frame(1), _frame(2)]


def test_cooldown_ignores_a_hit():
    model = ScriptedModel([0.99])
    guard = SessionGuard(10)
    guard.mark_failed(0)
    events = run_detection_loop([(1.0, _frame())], model, threshold=0.5, guard=guard)
    assert [(event.kind, event.reason) for event in events] == [("ignored", "cooldown")]


def test_active_call_ignores_a_hit():
    model = ScriptedModel([0.99])
    guard = SessionGuard(10)
    guard.mark_call_visible()
    events = run_detection_loop([(1.0, _frame())], model, threshold=0.5, guard=guard)
    assert events[0].reason == "call_active"


def test_buffer_holds_about_two_seconds_and_drops_older_frames():
    model = ScriptedModel([0.0] * 40)
    listener = WakeListener(model, threshold=0.5)
    for marker in range(30):
        listener.score(_frame(marker))
    assert BUFFER_FRAMES == 25
    assert len(listener.buffer) == 25
    assert listener.buffer[0][0] == 5  # frames 0..4 were dropped
    assert listener.buffer[-1][0] == 29


def test_scoring_does_not_write_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    model = ScriptedModel([0.2, 0.8])
    listener = WakeListener(model, threshold=0.5)
    listener.score(_frame())
    listener.score(_frame(3))
    assert list(tmp_path.iterdir()) == []


def test_reset_drops_buffered_audio():
    class ResettingModel:
        def __init__(self) -> None:
            self.resets = 0

        def predict(self, frame: bytes) -> dict[str, float]:
            return {"hey_jarvis": 0.0}

        def reset(self) -> None:
            self.resets += 1

    model = ResettingModel()
    listener = WakeListener(model, threshold=0.5)
    listener.score(_frame(4))
    assert len(listener.buffer) == 1
    listener.reset()
    assert len(listener.buffer) == 0
    assert model.resets == 1


def test_computer_style_trigger_waits_for_consecutive_frames():
    model = ScriptedModel([0.9, 0.9, 0.1, 0.9, 0.9, 0.9])
    guard = SessionGuard(10)
    frames = [(float(index), _frame(index)) for index in range(6)]
    events = run_detection_loop(
        frames, model, threshold=0.5, guard=guard, trigger_frames=3
    )
    assert [(event.kind, event.reason) for event in events] == [("accepted", "ok")]


def test_bad_frame_is_rejected():
    listener = WakeListener(ScriptedModel([0.0]), threshold=0.5)
    try:
        listener.score(b"nope")
    except ValueError as exc:
        assert "audio bytes" in str(exc)
    else:
        raise AssertionError("short frame should fail")
