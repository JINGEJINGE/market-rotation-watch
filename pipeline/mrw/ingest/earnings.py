"""US earnings calendar from yfinance, cached weekly in data/universe/earnings_US.csv.

Columns: ticker, date (YYYY-MM-DD), time ("BMO" / "AMC" / "" when Yahoo gives no time of day), fetched.
Refreshed by refresh-universe.yml (`run.py --earnings`) and opportunistically by the US run when the cache is older
than seven days. One sequential pass at Yahoo's pace, with a time budget so the US run never stalls on it; names not
reached keep their previous rows. Asian earnings dates from Yahoo are unreliable and are not fetched.
"""
from __future__ import annotations

import datetime as dt
import time

import pandas as pd

from ..config import UNIVERSE_DIR, log

EARNINGS_FILE = UNIVERSE_DIR / "earnings_US.csv"
MAX_AGE_DAYS = 7
COLS = ["ticker", "date", "time", "fetched"]


def load_earnings() -> pd.DataFrame:
    if not EARNINGS_FILE.exists():
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(EARNINGS_FILE, dtype={"ticker": str, "date": str, "time": str, "fetched": str}).fillna("")
    return df[COLS]


def cache_age_days() -> int | None:
    df = load_earnings()
    if df.empty:
        return None
    # age of the stalest name, so a pass cut short by the time budget is resumed by the next run
    per = df.assign(f=df["fetched"].replace("", "1970-01-01")).groupby("ticker")["f"].max()
    return (dt.date.today() - dt.date.fromisoformat(per.min())).days


def _time_of_day(ts: pd.Timestamp) -> str:
    try:
        ts = ts.tz_convert("America/New_York") if ts.tzinfo else ts
    except Exception:  # noqa: BLE001
        return ""
    if ts.hour == 0 and ts.minute == 0:
        return ""
    return "BMO" if ts.hour < 12 else ("AMC" if ts.hour >= 15 else "")


def _fetch_one(ticker: str) -> list[dict]:
    """Upcoming (and the most recent) earnings dates for one ticker. get_earnings_dates carries the time of day;
    Ticker.calendar is the fallback (date only)."""
    import yfinance as yf
    tk = yf.Ticker(ticker)
    today = pd.Timestamp.today().normalize()
    rows, failures = [], 0
    try:
        ed = tk.get_earnings_dates(limit=4)
        if ed is not None and len(ed):
            for ts in ed.index:
                ts = pd.Timestamp(ts)
                d = (ts.tz_convert("America/New_York") if ts.tzinfo else ts).tz_localize(None).normalize()
                if d >= today - pd.Timedelta(days=7):
                    rows.append({"date": d.strftime("%Y-%m-%d"), "time": _time_of_day(ts)})
    except Exception:  # noqa: BLE001
        rows, failures = [], failures + 1
    if not rows:
        try:
            cal = tk.calendar or {}
            for d in cal.get("Earnings Date", []) or []:
                d = pd.Timestamp(d).normalize()
                if d >= today - pd.Timedelta(days=7):
                    rows.append({"date": d.strftime("%Y-%m-%d"), "time": ""})
        except Exception as e:  # noqa: BLE001
            if failures:
                raise RuntimeError(f"both earnings endpoints failed for {ticker}") from e
    return [{"ticker": ticker, **r} for r in rows]


def refresh_earnings(tickers: list[str], budget_s: float = 900, pace: float = 0.6) -> dict:
    """Refresh the cache, oldest-fetched names first, within a time budget."""
    old = load_earnings()
    fetched_on = old.groupby("ticker")["fetched"].max().to_dict() if not old.empty else {}
    order = sorted(dict.fromkeys(tickers), key=lambda t: fetched_on.get(t, ""))
    today = dt.date.today().isoformat()
    t0, done, found, rows, errors, streak = time.time(), [], 0, [], 0, 0
    for t in order:
        if time.time() - t0 > budget_s:
            break
        if streak >= 25:  # Yahoo is refusing us: stop, and leave the unreached names stale for the next run
            log.warning("earnings calendar: %d consecutive failures, stopping", streak)
            break
        try:
            r = _fetch_one(t)
            streak = 0
        except Exception:  # noqa: BLE001
            errors += 1
            streak += 1
            time.sleep(pace)
            continue
        done.append(t)
        for x in r:
            rows.append({**x, "fetched": today})
        found += bool(r)
        # remember that the name was checked even when Yahoo lists no upcoming date
        if not r:
            rows.append({"ticker": t, "date": "", "time": "", "fetched": today})
        time.sleep(pace)
    if not done:
        rep = {"checked": 0, "of": len(order), "with_dates": 0, "errors": errors, "seconds": round(time.time() - t0, 1), "complete": False}
        log.warning("earnings calendar not refreshed: %s", rep)
        return rep
    new = pd.DataFrame(rows, columns=COLS)
    keep = old[~old["ticker"].isin(done)] if not old.empty else old
    out = pd.concat([keep, new], ignore_index=True).drop_duplicates(["ticker", "date"], keep="last")
    out = out.sort_values(["date", "ticker"])
    EARNINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    out[COLS].to_csv(EARNINGS_FILE, index=False)
    rep = {"checked": len(done), "of": len(order), "with_dates": found, "errors": errors,
           "seconds": round(time.time() - t0, 1), "complete": len(done) == len(order)}
    log.info("earnings calendar: %s", rep)
    return rep


def maybe_refresh(tickers: list[str], budget_s: float = 600) -> dict:
    age = cache_age_days()
    if age is not None and age < MAX_AGE_DAYS:
        return {"skipped": True, "age_days": age}
    return refresh_earnings(tickers, budget_s=budget_s)
