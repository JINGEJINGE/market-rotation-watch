"""Polite HTTP helper with retries, used by every ingester."""
from __future__ import annotations

import random
import time

import requests

from .config import DESKTOP_UA, log

_session = requests.Session()


def get(url: str, *, ua: str = DESKTOP_UA, headers: dict | None = None, params: dict | None = None,
        timeout: int = 30, retries: int = 3, pause: float = 0.0, expect_json: bool = False):
    """GET with retries and exponential backoff. Returns Response (or parsed JSON)."""
    h = {"User-Agent": ua, "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.8"}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(retries):
        try:
            if pause:
                time.sleep(pause + random.random() * pause)
            r = _session.get(url, headers=h, params=params, timeout=timeout)
            if r.status_code == 200 and (not expect_json or r.text.strip().startswith(("{", "["))):
                return r.json() if expect_json else r
            last = f"status={r.status_code} len={len(r.content)}"
        except requests.RequestException as e:  # noqa: PERF203
            last = repr(e)[:200]
        sleep = 2 ** attempt + random.random()
        log.warning("GET %s failed (%s), retry in %.1fs", url[:120], last, sleep)
        time.sleep(sleep)
    raise RuntimeError(f"GET failed after {retries} attempts: {url[:160]} ({last})")
