"""Telegram delivery. Silent no-op when the secrets are not configured."""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot{token}/{method}"
LIMIT = 4000


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
                print(f"[notify] failed: {e}")
                return None
            time.sleep(2 * (attempt + 1))


def send(text, chat_id=None, silent=False):
    """Send one message, splitting on paragraph boundaries if it is too long."""
    chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not chat:
        print(f"[notify] TELEGRAM_CHAT_ID unset — would have sent:\n{text}")
        return
    for chunk in _split(text):
        _post("sendMessage", {
            "chat_id": chat, "text": chunk, "parse_mode": "HTML",
            "disable_web_page_preview": "true",
            "disable_notification": "true" if silent else "false",
        })


def _split(text):
    if len(text) <= LIMIT:
        return [text]
    out, buf = [], ""
    for para in text.split("\n\n"):
        if len(buf) + len(para) + 2 > LIMIT:
            out.append(buf.rstrip())
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        out.append(buf.rstrip())
    return out


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
