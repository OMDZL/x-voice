"""Optional local beep when a wake phrase is accepted. No file is written."""

import logging
import sys


def play_chime(enabled: bool) -> None:
    if not enabled:
        return
    if sys.platform != "win32":
        logging.info("Chime skipped. The beep uses Windows only.")
        return
    import winsound

    # A generated tone. winsound.Beep does not create a sound file.
    winsound.Beep(880, 120)
