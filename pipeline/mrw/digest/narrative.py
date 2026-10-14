"""LLM narrative on top of the deterministic digest. The model only sees the digest tables and is
instructed to cite only numbers that appear there. Skipped silently if ANTHROPIC_API_KEY is absent."""
from __future__ import annotations

import os

from ..config import log

SYSTEM = """You are the rotation analyst for Market Rotation Watch, a personal research tool covering the US, Korea,
Hong Kong, Japan and Taiwan equity markets. You receive the day's computed digest tables. Write the morning/evening
read for an experienced investor.

Rules:
- Use ONLY numbers that appear in the tables. Never invent a figure, a flow, or an event.
- Open with the one-line regime verdict (rotation day vs beta day) and what drove it.
- Then: where capital is rotating in and out, and whether each move is CONFIRMED (turnover share rising, flows
  supportive, breadth participating, beta-adjusted residual positive) or UNCONFIRMED (price only, thin turnover,
  concentrated in one or two names). Say which.
- Cross-market: what the lead-lag table implies for the next session, or whether Asia followed the US move.
- End with 2-3 things to watch next session. No disclaimers, no hedging boilerplate, no bullet spam: short paragraphs.
- 220-320 words. Plain English. Numbers as in the tables (percentages with sign)."""


def write_narrative(digest_md: str, run: str) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        log.info("ANTHROPIC_API_KEY not set — skipping narrative")
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        model = os.environ.get("MRW_LLM_MODEL", "claude-sonnet-5-5")
        msg = client.messages.create(
            model=model, max_tokens=900, system=SYSTEM,
            messages=[{"role": "user", "content": f"Run: {'Asia close (evening, Singapore)' if run == 'asia' else 'US close (morning, Singapore)'}\n\n{digest_md}"}],
        )
        text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text").strip()
        return text or None
    except Exception as e:  # noqa: BLE001
        log.warning("narrative failed: %s", repr(e)[:200])
        return None
