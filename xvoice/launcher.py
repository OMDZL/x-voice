"""Open the Grok Bot chat link. Windows hands grokbot:// to the installed app."""

import sys

from xvoice.deeplink import DeepLinkError, build_launch_link


def open_prompt_link(bot_id: str) -> str:
    """Open the bot's prompt link with the marker text and return the link.

    The link is built here from the bot id, so a caller cannot pass a
    hand-built URL with other text.
    """
    link = build_launch_link(bot_id)
    if sys.platform != "win32":
        raise DeepLinkError(
            "Opening a grokbot:// link requires Windows, where Grok Bot is installed."
        )
    # os.startfile exists on Windows only. The platform check above keeps
    # this import from running anywhere else.
    import os

    os.startfile(link)  # type: ignore[attr-defined]
    return link
