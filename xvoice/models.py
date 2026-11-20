"""Find local wake-word files and load them. Nothing here downloads a model."""

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

# Spoken phrase for each built-in model. The openWakeWord names use the
# library's ONNX files. "computer" is computer_v2.onnx from Florian Wartner's
# MIT-licensed Home Assistant wake-word collection. See
# third_party/wakewords/LICENSE.txt.
PRETRAINED_MODELS = {
    "computer": "computer_v2.onnx",
    "hey_jarvis": "hey_jarvis_v0.1.onnx",
    "alexa": "alexa_v0.1.onnx",
    "hey_mycroft": "hey_mycroft_v0.1.onnx",
    "hey_rhasspy": "hey_rhasspy_v0.1.onnx",
    "timer": "timer_v0.1.onnx",
    "weather": "weather_v0.1.onnx",
}

SPOKEN_PHRASES = {
    "computer": "Computer",
    "hey_jarvis": "hey jarvis",
    "alexa": "alexa",
    "hey_mycroft": "hey mycroft",
    "hey_rhasspy": "hey rhasspy",
    "timer": "a timer phrase",
    "weather": "a weather phrase",
}

# "Computer" is an ordinary word, so a single loud frame is not enough.
# 0.75 is stricter than the other phrases, and 3 frames is about a quarter
# of a second of the score staying above that line.
MODEL_TUNING = {
    "computer": {"threshold": 0.75, "trigger_frames": 3},
}

COMPUTER_FILENAME = "computer_v2.onnx"
COMPUTER_SHA256 = "5e8157e8a0b2bbf4708452ccf8d0dc3397b6e81fba4dad097a8ba9192894ab3a"


def recommended_threshold(wake_model: str) -> float:
    return float(MODEL_TUNING.get(wake_model, {}).get("threshold", 0.5))


def recommended_trigger_frames(wake_model: str) -> int:
    return int(MODEL_TUNING.get(wake_model, {}).get("trigger_frames", 1))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ModelMissing(Exception):
    """A model file is not on disk. The runtime does not try to fetch it."""


@dataclass(frozen=True)
class ModelPaths:
    wake: Path
    melspec: Path
    embedding: Path
    wake_model: str


def bundled_models_dir() -> Path:
    """Folder of ONNX files shipped beside a frozen app, or ./models in a checkout."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "models"
    return Path.cwd() / "models"


def repo_wakeword_dir() -> Path:
    """Checked-in extra models, used when the app is not frozen."""
    return Path(__file__).resolve().parent.parent / "third_party" / "wakewords"


def resolve_model_paths(
    models_dir: Path,
    wake_model: str,
    extra_dirs: list[Path] | None = None,
) -> ModelPaths:
    """Return local ONNX paths, or raise ModelMissing with a setup hint."""
    root = models_dir.expanduser().resolve()
    name = wake_model.strip()
    if not name:
        raise ModelMissing("wake_model is empty.")

    filename = PRETRAINED_MODELS.get(name, name)
    if Path(filename).name != filename:
        raise ModelMissing(
            "wake_model must be a built-in name or a .onnx file name, not a path."
        )

    search = [root]
    if not getattr(sys, "frozen", False):
        search.append(repo_wakeword_dir())
    for extra in extra_dirs or []:
        search.append(extra.expanduser())
    wake = _find_file(filename, search)
    melspec = (root / "melspectrogram.onnx").resolve()
    embedding = (root / "embedding_model.onnx").resolve()
    missing = [path.name for path in (melspec, embedding) if not path.is_file()]
    if wake is None:
        missing.insert(0, filename)
    if missing:
        found = ", ".join(missing)
        raise ModelMissing(
            f"Wake-word model files are missing ({found}) in {root}. "
            "The app does not download them. Connect once and run: "
            "python -m xvoice.setup_models"
        )
    return ModelPaths(wake=wake, melspec=melspec, embedding=embedding, wake_model=name)


def _find_file(filename: str, directories: list[Path]) -> Path | None:
    for directory in directories:
        candidate = (directory / filename).resolve()
        root = directory.expanduser().resolve()
        if candidate != root and root not in candidate.parents:
            continue
        if candidate.is_file():
            return candidate
    return None


def load_wake_model(paths: ModelPaths):
    """Load openWakeWord from the files in `paths`.

    Import is inside the function so unit tests and Linux CI do not need the
    Windows audio stack or the model files. Feature models are passed by path.
    Voice activity detection and noise suppression stay off. Neither setting
    is required for the built-in phrases, and both would pull in more code.
    """
    from openwakeword.model import Model

    return Model(
        wakeword_models=[str(paths.wake)],
        inference_framework="onnx",
        melspec_model_path=str(paths.melspec),
        embedding_model_path=str(paths.embedding),
        vad_threshold=0,
        enable_speex_noise_suppression=False,
    )


class OpenWakeWordScorer:
    """Adapt openWakeWord's numpy input to the bytes the listener uses."""

    def __init__(self, model) -> None:
        self._model = model

    def reset(self) -> None:
        reset = getattr(self._model, "reset", None)
        if reset is not None:
            reset()

    def predict(self, frame: bytes) -> dict[str, float]:
        import numpy as np

        samples = np.frombuffer(frame, dtype="<i2")
        # Copy so the model cannot keep a view of a buffer the microphone reuses.
        samples = np.array(samples, copy=True)
        raw = self._model.predict(samples)
        if not isinstance(raw, dict):
            raise TypeError("Wake model returned an unexpected score.")
        scores: dict[str, float] = {}
        for key, value in raw.items():
            scores[str(key)] = _as_float(value)
        return scores


def _as_float(value: object) -> float:
    reshape = getattr(value, "reshape", None)
    if reshape is not None:
        flat = reshape(-1)
        if getattr(flat, "size", 0) == 0:
            return 0.0
        return float(flat.max())
    return float(value)  # type: ignore[arg-type]


def spoken_phrase(wake_model: str) -> str:
    return SPOKEN_PHRASES.get(wake_model, wake_model.replace("_", " "))
