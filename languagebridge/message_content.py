"""Build Matrix message payloads with optional subtle (secondary) styling."""

from __future__ import annotations

import html
import re

from mautrix.types import Format, MessageType, TextMessageEventContent

from languagebridge.config import UIConfig

_COLOR_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _safe_color(color: str, fallback: str) -> str:
    return color if _COLOR_HEX.match(color) else fallback


def text_content(body: str, msgtype: MessageType, ui: UIConfig) -> TextMessageEventContent:
    """Plain text, or HTML with muted color / small text for supporting clients."""
    if ui.message_style != "subtle":
        return TextMessageEventContent(msgtype=msgtype, body=body)

    color = _safe_color(ui.subtle_text_color, "#8E9597")
    escaped = html.escape(body, quote=False)
    inner = f"<small>{escaped}</small>" if ui.subtle_use_small else escaped
    formatted = f'<span data-mx-color="{color}">{inner}</span>'
    return TextMessageEventContent(
        msgtype=msgtype,
        body=body,
        format=Format.HTML,
        formatted_body=formatted,
    )
