"""System tray icon. pystray and Pillow are imported only when the tray starts."""

from __future__ import annotations


def start_tray(on_open, on_toggle_pause, on_quit, is_paused, state: str = "listening"):
    """Start the tray icon on its own thread and return the icon handle.

    `is_paused` is called when the menu opens so the label can switch between
    Pause and Resume.
    """
    import pystray

    icon = pystray.Icon(
        "x-voice",
        _image(state),
        _tooltip(state, is_paused()),
        menu=pystray.Menu(
            pystray.MenuItem("Open settings", lambda _icon, _item: on_open(), default=True),
            pystray.MenuItem(
                lambda _item: "Resume listening" if is_paused() else "Pause listening",
                lambda _icon, _item: on_toggle_pause(),
            ),
            pystray.MenuItem("Quit", lambda _icon, _item: on_quit()),
        ),
    )
    if hasattr(icon, "run_detached"):
        icon.run_detached()
    else:
        import threading

        threading.Thread(target=icon.run, name="xvoice-tray", daemon=True).start()
    return icon


def update_tray(icon, state: str, paused: bool) -> None:
    if icon is None:
        return
    try:
        icon.icon = _image(state)
        icon.title = _tooltip(state, paused)
        icon.update_menu()
    except Exception:
        # The tray thread may already be stopping.
        return


def stop_tray(icon) -> None:
    if icon is None:
        return
    try:
        icon.stop()
    except Exception:
        return


def _tooltip(state: str, paused: bool) -> str:
    if paused or state == "paused":
        return "x-voice — paused"
    if state == "in_call":
        return "x-voice — in a voice chat"
    if state == "permission":
        return "x-voice — microphone is blocked"
    if state in {"error", "mic_error"}:
        return "x-voice — needs attention"
    if state == "idle":
        return "x-voice — not listening"
    return "x-voice — listening"


def _image(state: str):
    from PIL import Image, ImageDraw

    color = {
        "listening": (46, 125, 50),
        "loading": (46, 125, 50),
        "triggered": (46, 125, 50),
        "cooldown": (46, 125, 50),
        "paused": (249, 168, 37),
        "in_call": (21, 101, 192),
        "permission": (198, 40, 40),
        "error": (198, 40, 40),
        "mic_error": (198, 40, 40),
    }.get(state, (96, 125, 139))
    image = Image.new("RGB", (64, 64), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill=color)
    return image
