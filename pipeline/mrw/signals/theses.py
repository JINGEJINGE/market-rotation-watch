"""Thesis tracker: named rotations opened by the pipeline from composite crossings and RRG entries with breadth
participating, carried day to day in data/outputs/theses.json.

Opening (sector and theme baskets, one open thesis per basket):
  positive  composite crosses up through +threshold,  or the RRG enters Leading with >= 60% of names above the 20DMA
  negative  composite crosses down through -threshold, or the RRG enters Lagging with <= 40% above the 20DMA
Status on each later session of the basket's own market:
  reversed    composite has the opposite sign
  fading      |composite| < threshold / 2, or breadth back through 50%, or the RRG has left the thesis' quadrants
  continuing  composite keeps the sign and the RRG is Leading/Improving (positive) or Lagging/Weakening (negative)
  closed      after 3 consecutive fading/reversed sessions, or 40 sessions open; kept under `closed` for 60 days
At most five theses stay open; when more qualify, the highest |composite| wins and the rest close as displaced.

State is replayed per market from `processed_through`, so re-running the same day is idempotent and a missed run
catches up. With no file yet, the tracker seeds itself by replaying the last 60 sessions of basket history.
"""
from __future__ import annotations

import datetime as dt
import json
from itertools import groupby

import numpy as np
import pandas as pd

from ..config import OUTPUT_DIR, PARAMS, write_json
from . import metrics as M

THESES_FILE = OUTPUT_DIR / "theses.json"
MAX_OPEN = 5
MAX_DAYS = 40
CLOSE_AFTER_BAD = 3
KEEP_CLOSED_DAYS = 60
SEED_SESSIONS = 60
BREADTH_ON, BREADTH_OFF, BREADTH_MID = 60.0, 40.0, 50.0
GOOD_QUADS = {1: ("Leading", "Improving"), -1: ("Lagging", "Weakening")}


def _f(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else v


def _load() -> dict | None:
    if not THESES_FILE.exists():
        return None
    try:
        return json.loads(THESES_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _row(h: pd.DataFrame, i: int) -> dict:
    r = h.iloc[i]
    return {"composite": _f(M.fl(r["composite"], 2)), "residual_5d_z": _f(M.fl(r.get("res5_z"), 2)),
            "turnover_quadrant": M.turnover_quadrant(r.get("rel5"), r.get("share_z")),
            "flow_z": _f(M.fl(r.get("flow_z"), 2)), "pct_above_20": _f(M.fl(r.get("pct_above_20"), 1)),
            "quadrant": r["quadrant"] if isinstance(r["quadrant"], str) else None}


def _trigger(h: pd.DataFrame, i: int, thr: float) -> tuple[int, str] | None:
    if i < 1:
        return None
    c, c0 = h["composite"].iloc[i], h["composite"].iloc[i - 1]
    q, q0 = h["quadrant"].iloc[i], h["quadrant"].iloc[i - 1]
    br = h["pct_above_20"].iloc[i]
    if pd.notna(c) and pd.notna(c0):
        if c >= thr > c0:
            return 1, f"composite crossed +{thr:g}"
        if c <= -thr < c0:
            return -1, f"composite crossed -{thr:g}"
    if isinstance(q, str) and q != q0 and pd.notna(br):
        if q == "Leading" and br >= BREADTH_ON:
            return 1, f"entered Leading with {br:.0f}% above 20DMA"
        if q == "Lagging" and br <= BREADTH_OFF:
            return -1, f"entered Lagging with {br:.0f}% above 20DMA"
    return None


def _status(t: dict, row: dict, thr: float) -> str:
    c, d, br, q = row["composite"], t["direction"], row["pct_above_20"], row["quadrant"]
    if c is not None and np.sign(c) == -d:
        return "reversed"
    if c is None or abs(c) < thr / 2:
        return "fading"
    if br is not None and ((d == 1 and br < BREADTH_MID) or (d == -1 and br > BREADTH_MID)):
        return "fading"
    if q in GOOD_QUADS[d]:
        return "continuing"
    return "fading"


def _note(t: dict) -> str:
    o, n = t["open_metrics"], t["current_metrics"]
    sign = "+" if t["direction"] == 1 else "−"
    parts = [f"{sign} opened {t['opened']} ({t['trigger']})"]
    parts.append(f"now {n['quadrant'] or 'n/a'}, composite {M.fl(n['composite'], 2) if n['composite'] is not None else 'n/a'}"
                 f" (open {o['composite'] if o['composite'] is not None else 'n/a'})")
    if n["pct_above_20"] is not None:
        parts.append(f"breadth {n['pct_above_20']:.0f}%")
    if t["since_open_residual"] is not None:
        parts.append(f"residual {t['since_open_residual'] * 100:+.1f}% since open")
    return "; ".join(parts)


def update_theses(results: list[dict], as_of: str) -> dict:
    """Advance the tracker through every session not yet processed and write data/outputs/theses.json."""
    thr = PARAMS["composite_threshold"]
    state = _load()
    seeded = state is None
    if seeded:
        state = {"open": [], "closed": [], "processed_through": {}}
    processed = dict(state.get("processed_through", {}))
    open_: dict[str, dict] = {t["basket"]: t for t in state.get("open", [])}
    closed: list[dict] = list(state.get("closed", []))

    hist: dict[str, tuple] = {}
    for r in results:
        b = r["basket"]
        if b.type not in ("sector", "theme"):
            continue
        h = r["history"].dropna(subset=["composite"])
        if len(h) < 2:
            continue
        hist[b.id] = (b, h)

    # the session grid to replay: for each market, sessions after processed_through (seed: the last 60 sessions)
    events: list[tuple[pd.Timestamp, str, int]] = []
    for bid, (b, h) in hist.items():
        start = processed.get(b.market)
        idx = h.index
        if start is None:
            pos = range(max(1, len(idx) - SEED_SESSIONS), len(idx))
        else:
            pos = range(int(idx.searchsorted(pd.Timestamp(start), side="right")), len(idx))
        events.extend((idx[i], bid, i) for i in pos)
    events.sort(key=lambda e: (e[0], e[1]))

    def close(t: dict, day: str, reason: str) -> None:
        t["status"], t["closed"], t["close_reason"] = "closed", day, reason
        closed.append(t)
        open_.pop(t["basket"], None)

    for day, grp in groupby(events, key=lambda e: e[0]):
        dstr = pd.Timestamp(day).strftime("%Y-%m-%d")
        for _, bid, i in grp:
            b, h = hist[bid]
            row = _row(h, i)
            t = open_.get(bid)
            if t is not None:
                t["days_open"] += 1
                res = h["residual"].iloc[i]
                if pd.notna(res):
                    t["since_open_residual"] = round((t["since_open_residual"] or 0.0) + float(res), 5)
                t["status"] = _status(t, row, thr)
                t["bad_streak"] = t["bad_streak"] + 1 if t["status"] in ("fading", "reversed") else 0
                t["last_update"], t["current_metrics"] = dstr, row
                t["note"] = _note(t)
                if t["bad_streak"] >= CLOSE_AFTER_BAD:
                    close(t, dstr, f"{t['status']} for {CLOSE_AFTER_BAD} sessions")
                elif t["days_open"] >= MAX_DAYS:
                    close(t, dstr, f"{MAX_DAYS} sessions open")
                continue
            trig = _trigger(h, i, thr)
            if trig is None:
                continue
            direction, why = trig
            t = {"id": f"{bid}@{dstr}", "basket": bid, "name": b.name, "market": b.market, "type": b.type,
                 "direction": direction, "opened": dstr, "trigger": why, "open_metrics": row, "current_metrics": row,
                 "status": "new", "last_update": dstr, "days_open": 0, "since_open_residual": 0.0, "bad_streak": 0}
            t["note"] = _note(t)
            open_[bid] = t
        # cap the open list: highest |composite| wins. A candidate opened today that does not make the cut is simply
        # not opened; an older thesis pushed out by a stronger newcomer is closed as displaced.
        if len(open_) > MAX_OPEN:
            ranked = sorted(open_.values(), key=lambda t: abs(t["current_metrics"]["composite"] or 0), reverse=True)
            for t in ranked[MAX_OPEN:]:
                if t["opened"] == dstr and t["days_open"] == 0:
                    open_.pop(t["basket"], None)
                else:
                    close(t, dstr, f"displaced (max {MAX_OPEN} open)")
    for bid, (b, h) in hist.items():
        processed[b.market] = max(processed.get(b.market, ""), h.index[-1].strftime("%Y-%m-%d"))

    cutoff = (pd.Timestamp(as_of) - pd.Timedelta(days=KEEP_CLOSED_DAYS)).strftime("%Y-%m-%d")
    closed = [t for t in closed if t.get("closed", "") >= cutoff]
    out = {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "as_of": as_of,
        "seeded_this_run": seeded,
        "rules": {"threshold": thr, "breadth_on": BREADTH_ON, "breadth_off": BREADTH_OFF, "max_open": MAX_OPEN,
                  "max_days": MAX_DAYS, "close_after_bad_sessions": CLOSE_AFTER_BAD, "keep_closed_days": KEEP_CLOSED_DAYS},
        "processed_through": processed,
        "open": sorted(open_.values(), key=lambda t: abs(t["current_metrics"]["composite"] or 0), reverse=True),
        "closed": sorted(closed, key=lambda t: t["closed"], reverse=True),
    }
    write_json(THESES_FILE, out)
    return out
