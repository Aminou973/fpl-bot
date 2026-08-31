"""Telegram delivery, routed by alert tier.

Three tiers, so the phone can be configured to only ring for what matters:

- ``alert`` — things worth interrupting for: the plan when it changed, the
  deadline warning, a lineup applied or failed, weekly results. Delivered
  with sound, to TELEGRAM_CHAT_ALERT (falling back to TELEGRAM_CHAT_ID).
- ``live``  — matchday scores. Silent, to TELEGRAM_CHAT_LIVE if set.
- ``watch`` — prices and team-news noise. Silent, to TELEGRAM_CHAT_WATCH
  if set.

Without the optional per-tier secrets everything lands in the one default
chat, with only the alert tier audible.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot{token}/{method}"
LIMIT = 4000

# tier -> (silent by default, chat env var checked in order)
TIERS = {
    "alert": (False, ["TELEGRAM_CHAT_ALERT", "TELEGRAM_CHAT_ID"]),
    "live": (True, ["TELEGRAM_CHAT_LIVE", "TELEGRAM_CHAT_ID"]),
    "watch": (True, ["TELEGRAM_CHAT_WATCH", "TELEGRAM_CHAT_ID"]),
}


def _post(method, payload):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print(f"[notify] TELEGRAM_BOT_TOKEN unset — would have sent:\n{payload.get('text','')}")
        return None
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(API.format(token=token, method=method), data=data)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:                       # noqa: BLE001
            if attempt == 2:
                # Telegram names the real reason (a bad HTML entity, and its
                # byte offset) in the response body, not in the status line
                body = ""
                try:
                    body = e.read().decode("utf-8", "replace")[:300]
                except Exception:                    # noqa: BLE001
                    pass
                print(f"[notify] failed: {e}" + (f" | {body}" if body else ""))
                return None
            time.sleep(2 * (attempt + 1))


def send(text, chat_id=None, silent=None, kind="alert"):
    """Send one message (split on paragraphs if too long).

    ``kind`` routes the message to its tier's chat and sound setting; an
    explicit ``silent`` or ``chat_id`` argument overrides the tier.
    """
    silent_by_tier, envs = TIERS.get(kind, (False, ["TELEGRAM_CHAT_ID"]))
    chat = chat_id
    if not chat:
        for env in envs:
            chat = os.environ.get(env)
            if chat:
                break
    if not chat:
        print(f"[notify] no chat configured for tier '{kind}' — would have sent:\n{text}")
        return
    if silent is None:
        silent = silent_by_tier
    for chunk in _split(text):
        _post("sendMessage", {
            "chat_id": chat, "text": chunk, "parse_mode": "HTML",
            "disable_web_page_preview": "true",
            "disable_notification": "true" if silent else "false",
        })


def _split(text):
    """Chunks Telegram will actually accept: never empty, never over LIMIT.

    Splitting on paragraphs alone is not enough - a single paragraph longer
    than LIMIT used to be flushed while the buffer was still empty (Telegram
    rejects an empty message) and then sent whole (Telegram rejects anything
    over 4096). Both cases now fall through to a hard character split.
    """
    if len(text) <= LIMIT:
        return [text]
    out, buf = [], ""
    for para in text.split("\n\n"):
        while len(para) > LIMIT:                 # a single huge paragraph
            if buf.strip():
                out.append(buf.rstrip())
                buf = ""
            out.append(para[:LIMIT])
            para = para[LIMIT:]
        if buf and len(buf) + len(para) + 2 > LIMIT:
            out.append(buf.rstrip())
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        out.append(buf.rstrip())
    return [c for c in out if c.strip()]


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
