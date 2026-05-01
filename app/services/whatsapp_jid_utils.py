from __future__ import annotations


def isGroupJid(jid: str) -> bool:
    """Returns True when JID targets a WhatsApp group."""
    return str(jid or "").strip().lower().endswith("@g.us")


def is_group_jid(jid: str) -> bool:
    return isGroupJid(jid)
