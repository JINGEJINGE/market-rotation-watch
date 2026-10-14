"""Daily close/volume ingestion via yfinance, stored as monthly parquet partitions.

Layout: data/prices/{GROUP}/{YYYY-MM}.parquet with columns [date, ticker, close, volume].
GROUP is the market code for universe constituents, or XTRA for benchmarks, FX, reference
tickers and theme members that sit outside the sector universes. A daily run rewrites only
the current month's files, so the git history stays small.
"""
from __future__ import annotations

import datetime as dt
import time

import pandas as pd
import yfinance as yf

from ..config import MARKETS, PARAMS, PRICES_DIR, REFERENCE_TICKERS, log
from ..universe.build import load_all_universes, theme_tickers

BATCH = 150


def ticker_groups() -> dict[str, list[str]]:
    uni = load_all_universes()
    groups: dict[str, list[str]] = {m: uni.loc[uni.market == m, "ticker"].tolist() for m in MARKETS}
    in_universe = set(uni["ticker"])
    xtra = []
    for m, c in MARKETS.items():
        xtra.append(c["benchmark"])
        if c.get("fx"):
            xtra.append(c["fx"])
    xtra += REFERENCE_TICKERS
    xtra += [t for t in theme_tickers() if t not in in_universe]
    groups["XTRA"] = list(dict.fromkeys(xtra))
    return groups


def _download(tickers: list[str], start: dt.date | None, period: str | None) -> pd.DataFrame:
    frames = []
    for i in range(0, len(tickers), BATCH):
        chunk = tickers[i:i + BATCH]
        raw = None
        for attempt in range(4):
            limited = False
            try:
                raw = yf.download(chunk, start=start, period=period if start is None else None, interval="1d",
                                  auto_adjust=True, progress=False, threads=True, group_by="column")
            except Exception as e:  # noqa: BLE001
                limited = "RateLimit" in type(e).__name__ or "Too Many" in str(e)
                log.warning("yfinance batch failed (%s)", repr(e)[:100])
                raw = None
            if raw is not None and not raw.empty and raw["Close"].notna().any().any():
                break
            if not limited and attempt >= 1:
                break  # genuinely no data (delisted / bad symbol): don't keep waiting
            wait = 60 * (attempt + 1)
            log.warning("empty/rate-limited batch (%d tickers), sleeping %ds", len(chunk), wait)
            time.sleep(wait)
        if raw is None or raw.empty:
            continue
        if not isinstance(raw.columns, pd.MultiIndex):  # single ticker
            raw.columns = pd.MultiIndex.from_product([raw.columns, chunk])
        close = raw["Close"].stack(future_stack=True).rename("close")
        vol = raw["Volume"].stack(future_stack=True).rename("volume")
        df = pd.concat([close, vol], axis=1).reset_index()
        df.columns = ["date", "ticker", "close", "volume"]
        df = df.dropna(subset=["close"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
        frames.append(df)
        time.sleep(2.0)
    if not frames:
        return _empty_prices()
    return pd.concat(frames, ignore_index=True)


def _empty_prices() -> pd.DataFrame:
    """Typed empty frame so concatenation never degrades the date column to object dtype."""
    return pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "ticker": pd.Series(dtype="object"),
                         "close": pd.Series(dtype="float64"), "volume": pd.Series(dtype="float64")})


def _load_group(group: str) -> pd.DataFrame:
    d = PRICES_DIR / group
    files = sorted(d.glob("*.parquet")) if d.exists() else []
    if not files:
        return _empty_prices()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _save_group(group: str, df: pd.DataFrame, months: set[str] | None = None) -> None:
    d = PRICES_DIR / group
    d.mkdir(parents=True, exist_ok=True)
    df = df.drop_duplicates(["date", "ticker"], keep="last").sort_values(["date", "ticker"])
    df["month"] = df["date"].dt.strftime("%Y-%m")
    for m, part in df.groupby("month"):
        if months is None or m in months:
            part.drop(columns=["month"]).reset_index(drop=True).to_parquet(d / f"{m}.parquet", index=False)


def update_prices(full: bool = False) -> dict:
    """Incrementally update all groups. Returns a freshness report."""
    report = {}
    years = PARAMS["history_years"]
    for group, tickers in ticker_groups().items():
        if not tickers:
            continue
        try:
            report[group] = _update_group(group, tickers, full, years)
        except Exception as e:  # noqa: BLE001
            # one market's failure must not abandon the others; the digest's data note reports it
            log.error("%s: price update failed: %s", group, repr(e)[:200])
            report[group] = {"tickers": len(tickers), "updated": False, "error": repr(e)[:200]}
    return report


def _update_group(group: str, tickers: list[str], full: bool, years: float) -> dict:
    existing = _load_group(group)
    if not existing.empty:
        existing["date"] = pd.to_datetime(existing["date"])
    if full or existing.empty:
        start = (pd.Timestamp.today() - pd.Timedelta(days=int(years * 365))).date()
        new = _download(tickers, start, None)
    else:
        last = existing["date"].max()
        start = (last - pd.Timedelta(days=7)).date()
        missing = sorted(set(tickers) - set(existing["ticker"]))
        new = _download(tickers, start, None)
        if missing:  # new constituents: backfill their history
            log.info("%s: backfilling %d new tickers", group, len(missing))
            hist_start = (pd.Timestamp.today() - pd.Timedelta(days=int(years * 365))).date()
            hist = _download(missing, hist_start, None)
            if hist.empty:
                log.warning("%s: no history for new tickers %s (delisted or bad symbols?)", group, missing[:10])
            else:
                new = pd.concat([new, hist], ignore_index=True)
    if new.empty:
        log.warning("%s: no new price data", group)
        return {"tickers": len(tickers), "last_date": str(existing["date"].max().date()) if not existing.empty else None, "updated": False}
    new["date"] = pd.to_datetime(new["date"])
    merged = pd.concat([existing, new], ignore_index=True)
    merged["date"] = pd.to_datetime(merged["date"])
    try:
        merged = _fill_gaps_from_intraday(group, tickers, merged)
    except Exception as e:  # noqa: BLE001
        log.warning("%s: intraday gap fill failed: %s", group, repr(e)[:120])
    months = None if (full or existing.empty) else set(merged["date"].dt.strftime("%Y-%m")) & set(new["date"].dt.strftime("%Y-%m")) | {pd.Timestamp.today().strftime("%Y-%m")}
    _save_group(group, merged, months)
    got = new["ticker"].nunique()
    log.info("%s: %d/%d tickers, last date %s", group, got, len(tickers), new["date"].max().date())
    return {"tickers": len(tickers), "with_data": int(got), "last_date": str(new["date"].max().date()), "updated": True}


def _fill_gaps_from_intraday(group: str, tickers: list[str], merged: pd.DataFrame) -> pd.DataFrame:
    """Yahoo sometimes omits a completed Asian session from its daily bars while the intraday bars exist.
    For the last few sessions of a market, if fewer than half the universe has a daily bar, rebuild the bar
    from 1-hour data (close = last bar, volume = sum of bars)."""
    if group not in MARKETS:
        return merged
    import exchange_calendars as xc
    cal = xc.get_calendar(MARKETS[group]["calendar"])
    tz = MARKETS[group]["tz"]
    now = pd.Timestamp.now(tz=tz)
    end = now.normalize().tz_localize(None)
    sessions = cal.sessions_in_range(end - pd.Timedelta(days=12), end)
    sessions = [s for s in sessions if cal.session_close(s) < pd.Timestamp.now(tz="UTC")]
    have = merged.groupby("date")["ticker"].nunique()
    missing = [s for s in sessions[-6:] if have.get(pd.Timestamp(s), 0) < 0.5 * len(tickers)]
    if not missing:
        return merged
    rows = []
    for s in missing:
        start = pd.Timestamp(s).tz_localize(tz)
        stop = start + pd.Timedelta(days=1)
        log.info("%s: rebuilding %s from intraday bars", group, s.date())
        for i in range(0, len(tickers), BATCH):
            chunk = tickers[i:i + BATCH]
            try:
                raw = yf.download(chunk, start=start, end=stop, interval="1h", auto_adjust=True, progress=False,
                                  threads=True, group_by="column")
            except Exception as e:  # noqa: BLE001
                log.warning("intraday fill failed: %s", repr(e)[:100])
                continue
            if raw is None or raw.empty:
                continue
            if not isinstance(raw.columns, pd.MultiIndex):
                raw.columns = pd.MultiIndex.from_product([raw.columns, chunk])
            close = raw["Close"].ffill().iloc[-1]
            vol = raw["Volume"].sum(min_count=1)
            for t in chunk:
                if t in close.index and pd.notna(close[t]):
                    rows.append({"date": pd.Timestamp(s), "ticker": t, "close": float(close[t]), "volume": float(vol.get(t, float("nan")))})
            time.sleep(1.0)
    if not rows:
        return merged
    fill = pd.DataFrame(rows)
    log.info("%s: filled %d bars from intraday", group, len(fill))
    # keep existing daily bars where present; only add missing (date, ticker) pairs
    key = merged.set_index(["date", "ticker"]).index
    fill = fill[~fill.set_index(["date", "ticker"]).index.isin(key)]
    return pd.concat([merged, fill], ignore_index=True)


def load_prices(groups: list[str] | None = None) -> pd.DataFrame:
    groups = groups or [p.name for p in PRICES_DIR.iterdir() if p.is_dir()]
    df = pd.concat([_load_group(g) for g in groups], ignore_index=True)
    return df.drop_duplicates(["date", "ticker"], keep="last")


def wide(df: pd.DataFrame, col: str = "close") -> pd.DataFrame:
    return df.pivot(index="date", columns="ticker", values=col).sort_index()
