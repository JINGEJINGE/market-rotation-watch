"""Telegram delivery. Skipped silently if TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are absent."""
from __future__ import annotations

import os
from pathlib import Path

import requests

from ..config import log

MAX = 4000


def _creds() -> tuple[str, str] | None:
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        log.info("Telegram credentials not set — skipping push")
        return None
    return tok, chat


def _chunks(text: str) -> list[str]:
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > MAX:
            out.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return out


def send_text(text: str) -> bool:
    c = _creds()
    if not c:
        return False
    tok, chat = c
    ok = True
    for chunk in _chunks(text):
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": chunk, "disable_web_page_preview": True}, timeout=30)
        if r.status_code != 200:
            log.warning("telegram sendMessage failed: %s %s", r.status_code, r.text[:200])
            ok = False
    return ok


def send_photo(path: Path, caption: str = "") -> bool:
    c = _creds()
    if not c or not path.exists():
        return False
    tok, chat = c
    with open(path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendPhoto", data={"chat_id": chat, "caption": caption[:1000]},
                          files={"photo": f}, timeout=60)
    if r.status_code != 200:
        log.warning("telegram sendPhoto failed: %s %s", r.status_code, r.text[:200])
        return False
    return True
