"""One-time download of the openWakeWord ONNX models.

Run this yourself while the PC is online:

    python -m xvoice.setup_models

The listener never calls this module. Model files are checked against the
hashes below and saved under the models folder. Audio is not involved.
"""

import argparse
import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

# These URLs are the ONNX assets from the openWakeWord v0.5.1 release, which
# is the set openWakeWord 0.6.0 downloads. Hashes were recorded from those files.
MODEL_BASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/"

FILES = {
    "melspectrogram.onnx": "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f",
    "embedding_model.onnx": "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f",
    "hey_jarvis_v0.1.onnx": "94a13cfe60075b132f6a472e7e462e8123ee70861bc3fb58434a73712ee0d2cb",
    "alexa_v0.1.onnx": "6ff566a01d12670e8d9e3c59da32651db1575d17272a601b7f8a39283dfbae3e",
    "hey_mycroft_v0.1.onnx": "c2a311e8fa1338de89c31b3b46dc4dffd4af2f9a8d6ddead48893c2d301b1f18",
    "hey_rhasspy_v0.1.onnx": "5a9b3ed3be2910e35780e097905aa9f35a9c10038df47914cf2b3ec4d670f6ea",
    "timer_v0.1.onnx": "371e44535470a29248b3b8f1bbbbaf2525c86417fd8f75c67fcf02ae0b9626df",
    "weather_v0.1.onnx": "8441da8e746899e8d969528d5bad5651cdd563079c05962788f77753041f60e7",
}


class SetupError(Exception):
    """The one-time model setup could not finish."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def missing_or_damaged(directory: Path) -> list[str]:
    """Names of model files that are absent or do not match the recorded hash."""
    bad: list[str] = []
    for name, digest in FILES.items():
        path = directory / name
        if not path.is_file() or sha256_file(path) != digest:
            bad.append(name)
    return bad


def ensure_models(directory: Path, check_only: bool = False) -> None:
    """Download any missing model into `directory`, or only check when asked."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in missing_or_damaged(directory):
        path = directory / name
        if check_only:
            raise SetupError(
                f"Missing or damaged model file: {path}. "
                "Run: python -m xvoice.setup_models"
            )
        print(f"Downloading {name}")
        _download(MODEL_BASE + name, path, FILES[name])
        print(f"Saved {name}")
    print(f"Model files are ready in {directory.resolve()}")
    print("x-voice will not download anything when you run it.")


def _download(url: str, dest: Path, digest: str) -> None:
    temporary = dest.with_name(dest.name + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": "x-voice-setup"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                handle.write(chunk)
        actual = sha256_file(temporary)
        if actual != digest:
            temporary.unlink(missing_ok=True)
            raise SetupError(
                f"Download for {dest.name} did not match the expected file. Nothing was kept."
            )
        temporary.replace(dest)
    except SetupError:
        raise
    except urllib.error.URLError as exc:
        temporary.unlink(missing_ok=True)
        raise SetupError(
            f"Could not download {dest.name}. Check the network and run the setup again. Details: {exc}"
        ) from exc
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise SetupError(f"Could not save {dest.name}. Details: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download openWakeWord models once. Later runs of x-voice stay offline."
    )
    parser.add_argument(
        "--dir",
        default="models",
        help="Folder to store the model files. Default: models",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check the local files and do not download.",
    )
    args = parser.parse_args(argv)
    try:
        ensure_models(Path(args.dir), check_only=args.check)
    except SetupError as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
