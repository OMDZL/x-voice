"""Copy a user-chosen ONNX wake model into the per-user models folder.

Nothing here downloads a file. The chosen file is checked, then copied.
"""

from pathlib import Path

CUSTOM_OPTION = "Custom wake word file (.onnx)…"
MIN_ONNX_BYTES = 10_000
MAX_ONNX_BYTES = 20_000_000


class ModelImportError(Exception):
    """The chosen file cannot be used as a wake model."""


def is_safe_onnx_name(name: str) -> bool:
    """True when `name` is a single .onnx file name, not a path."""
    if not name or name != Path(name).name:
        return False
    if name.startswith(".") or ".." in name:
        return False
    return name.lower().endswith(".onnx")


def custom_model_label(filename: str) -> str:
    stem = Path(filename).stem.replace("_", " ").strip()
    return stem or filename


def wake_menu(custom_filenames: list[str]) -> list[tuple[str, str]]:
    """Dropdown rows: label, stored wake_model value.

    Built-in phrases come first, then files already copied for this user,
    then the entry that opens a file picker.
    """
    from xvoice.models import PRETRAINED_MODELS, spoken_phrase

    rows = [(spoken_phrase(name), name) for name in PRETRAINED_MODELS]
    used = {label for label, _value in rows}
    for filename in custom_filenames:
        if not is_safe_onnx_name(filename):
            continue
        label = custom_model_label(filename)
        if label in used:
            label = f"{label} ({filename})"
        used.add(label)
        rows.append((label, filename))
    rows.append((CUSTOM_OPTION, CUSTOM_OPTION))
    return rows


def list_custom_models(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    names = [path.name for path in directory.glob("*.onnx") if path.is_file() and is_safe_onnx_name(path.name)]
    return sorted(names)


def validate_onnx_file(path: Path) -> None:
    if not path.is_file():
        raise ModelImportError("Choose an existing .onnx file.")
    if path.suffix.lower() != ".onnx":
        raise ModelImportError("The wake word file must end in .onnx.")
    size = path.stat().st_size
    if size < MIN_ONNX_BYTES or size > MAX_ONNX_BYTES:
        raise ModelImportError(
            "That file is the wrong size for a wake-word model. "
            "Choose the .onnx file, not a zip or a text file."
        )
    sample = path.read_bytes()[:64]
    if sample and all(byte in (9, 10, 13) or 32 <= byte < 127 for byte in sample):
        raise ModelImportError("That file is text, not an ONNX wake-word model.")


def import_custom_model(source: Path, dest_dir: Path) -> str:
    """Validate `source` and copy it into `dest_dir`. Return the stored file name."""
    validate_onnx_file(source)
    stored_name = _stored_name(source.name)
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = (dest_dir / stored_name).resolve()
    if dest_dir.resolve() not in destination.parents:
        raise ModelImportError("Could not store that model file.")
    destination.write_bytes(source.read_bytes())
    return stored_name


def _stored_name(original: str) -> str:
    base = Path(original).name
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in base)
    if not is_safe_onnx_name(cleaned):
        raise ModelImportError("The wake word file needs a usable .onnx name.")
    return cleaned
