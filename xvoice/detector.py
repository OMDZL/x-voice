"""Score microphone frames with a wake model. Frames stay in memory.

The listener keeps about two seconds of recent frames in a fixed-size queue
and drops anything older. The queue is never written to disk, logged, or sent.
openWakeWord also keeps its own feature state in memory; this module does not
copy that state out.
"""

from collections import deque
from dataclasses import dataclass

from xvoice.guard import SessionGuard

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80 ms at 16 kHz
BUFFER_SECONDS = 2
BUFFER_FRAMES = int(BUFFER_SECONDS / (FRAME_SAMPLES / SAMPLE_RATE))


@dataclass(frozen=True)
class DetectionEvent:
    kind: str  # "accepted" or "ignored"
    score: float
    reason: str


class WakeListener:
    """Score one 80 ms frame at a time against a threshold."""

    def __init__(
        self,
        model,
        threshold: float,
        frame_samples: int = FRAME_SAMPLES,
        trigger_frames: int = 1,
    ) -> None:
        if threshold <= 0 or threshold > 1:
            raise ValueError("threshold must be greater than 0 and at most 1.")
        if trigger_frames < 1:
            raise ValueError("trigger_frames must be at least 1.")
        self.model = model
        self.threshold = float(threshold)
        self.frame_samples = frame_samples
        self.trigger_frames = int(trigger_frames)
        self.buffer: deque[bytes] = deque(maxlen=BUFFER_FRAMES)
        self._streak = 0

    def reset(self) -> None:
        """Drop buffered audio so a later session cannot re-score it."""
        self.buffer.clear()
        self._streak = 0
        reset = getattr(self.model, "reset", None)
        if reset is not None:
            reset()

    def observe(self, frame: bytes) -> tuple[float, bool]:
        """Score one frame. The second value is true only after enough hits in a row."""
        score = self.score(frame)
        if score >= self.threshold:
            self._streak += 1
        else:
            self._streak = 0
        return score, self._streak >= self.trigger_frames

    def score(self, frame: bytes) -> float:
        expected = self.frame_samples * 2  # 16-bit samples
        if not isinstance(frame, (bytes, bytearray)):
            raise TypeError("An audio frame must be bytes.")
        if len(frame) != expected:
            raise ValueError(f"Expected {expected} audio bytes, got {len(frame)}.")
        # Copy into the rolling buffer. The oldest frame is dropped when full.
        self.buffer.append(bytes(frame))
        prediction = self.model.predict(self.buffer[-1])
        if not isinstance(prediction, dict) or not prediction:
            return 0.0
        return max(float(value) for value in prediction.values())


def run_detection_loop(
    frames,
    model,
    threshold: float,
    guard: SessionGuard,
    trigger_frames: int = 1,
) -> list[DetectionEvent]:
    """Score (time, frame) pairs and apply the guard to each hit.

    `frames` is an iterable of (timestamp, frame_bytes). The model is any
    object with predict(frame) -> dict[str, float]. A phrase is accepted only
    after `trigger_frames` scores in a row meet the threshold. That acceptance
    starts an attempt so the following hits are ignored until the guard allows
    another.
    """
    listener = WakeListener(model, threshold, trigger_frames=trigger_frames)
    events: list[DetectionEvent] = []
    for now, frame in frames:
        score, ready = listener.observe(frame)
        if not ready:
            continue
        allowed, reason = guard.allow_trigger(now)
        if not allowed:
            events.append(DetectionEvent("ignored", score, reason))
            continue
        guard.begin_attempt(now)
        events.append(DetectionEvent("accepted", score, "ok"))
    return events
