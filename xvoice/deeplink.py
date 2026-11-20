"""Build the Grok Bot deep links.

Grok Bot ignores a prompt link without text, so the link x-voice opens carries
one fixed marker word, MARKER_TEXT. Grok Bot then switches to the bot and puts
the marker in its message box (after a confirmation dialog, some of the time).
Seeing exactly the marker in the message box is how x-voice knows the right
bot's chat is showing. The marker is removed before Start voice chat is
pressed. No other text can be put in the link.
"""

from urllib.parse import parse_qsl, quote, unquote, urlsplit

PLACEHOLDER_BOT_ID = "PASTE_BOT_ID_HERE"

# The only text x-voice ever puts in a link. Plain ASCII, so Grok Bot's check
# for hidden characters has nothing to object to.
MARKER_TEXT = "x-voice"

# Characters that would add another query parameter, a fragment, or a path.
_UNSAFE = set("?#&=\r\n\t /\\")


class DeepLinkError(ValueError):
    """The bot id cannot be turned into an id-only grokbot:// link."""


def extract_bot_id(raw: str) -> str:
    """Turn a bare id, a share link, or a grokbot:// link into the bare id.

    A share link's query may include other parameters. Only the id is kept.
    The result is checked with the same rules as the deep link builder, so a
    value that would add a text parameter is rejected.
    """
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    if not text:
        raise DeepLinkError("Enter the bot id, or paste the bot's share link.")
    if text == PLACEHOLDER_BOT_ID:
        raise DeepLinkError(
            "That is still the placeholder. Paste the bot id or the share link."
        )

    candidate = text
    if "://" in text or text.startswith("grokbot:") or "/" in text or "\\" in text or "?" in text:
        normalized = text.replace("\\", "/")
        if "://" not in normalized:
            # A schemeless path still needs a scheme so the id can be read from it.
            normalized = "https:" + "//" + normalized.lstrip("/")
        parts = urlsplit(normalized)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        found = query.get("id", "").strip()
        if found:
            candidate = found
        else:
            segments = [unquote(segment) for segment in parts.path.split("/") if segment]
            if not segments:
                raise DeepLinkError(
                    "That link has no bot id. Paste the share link, or only the id at the end of it."
                )
            candidate = segments[-1].strip()
    return _validated_bare_id(candidate)


def _validated_bare_id(candidate: str) -> str:
    link = build_prompt_link(candidate)
    parsed = dict(parse_qsl(urlsplit(link).query, keep_blank_values=True))
    return parsed["id"]


def build_prompt_link(bot_id: str) -> str:
    """Return `grokbot://app/v1/prompt?id=<bot-id>` with no text parameter."""
    cleaned = bot_id.strip()
    if not cleaned:
        raise DeepLinkError("bot_id is empty.")
    if cleaned == PLACEHOLDER_BOT_ID:
        raise DeepLinkError(
            "bot_id is still PASTE_BOT_ID_HERE. Paste the id from the bot's share link."
        )
    if any(ord(char) < 32 for char in cleaned) or any(char in _UNSAFE for char in cleaned):
        raise DeepLinkError(
            "bot_id must be the id alone. Paste the last part of the share link, "
            "after the final slash, with no spaces or extra query text."
        )

    encoded = quote(cleaned, safe="")
    link = f"grokbot://app/v1/prompt?id={encoded}"
    _assert_id_only(link, cleaned)
    return link


def _assert_id_only(link: str, bot_id: str) -> None:
    parts = urlsplit(link)
    if parts.scheme != "grokbot" or parts.netloc != "app" or parts.path != "/v1/prompt":
        raise DeepLinkError("Refusing to build a link that is not a Grok Bot prompt link.")
    if parts.fragment:
        raise DeepLinkError("Refusing to build a link with a fragment.")
    query = parse_qsl(parts.query, keep_blank_values=True)
    names = [name for name, _value in query]
    if names != ["id"]:
        raise DeepLinkError("Refusing to build a link with any parameter other than id.")
    if query[0][1] != bot_id:
        raise DeepLinkError("Refusing to build a link whose id does not match bot_id.")
    if "text=" in link.lower():
        raise DeepLinkError("Refusing to build a link that includes text.")


def build_launch_link(bot_id: str) -> str:
    """Return `grokbot://app/v1/prompt?id=<bot-id>&text=x-voice`.

    The id is checked by build_prompt_link. The text is always MARKER_TEXT.
    """
    base = build_prompt_link(bot_id)
    link = f"{base}&text={quote(MARKER_TEXT, safe='')}"
    parts = urlsplit(link)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if [name for name, _value in query] != ["id", "text"]:
        raise DeepLinkError("Refusing to build a link with unexpected parameters.")
    if query[0][1] != bot_id.strip() or query[1][1] != MARKER_TEXT:
        raise DeepLinkError("Refusing to build a link whose id or text was changed.")
    return link
