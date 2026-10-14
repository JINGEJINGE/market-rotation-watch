"""Market overview blocks for latest.json (`us_overview` on the US run, `asia_overview` on the Asia run).

These replace the memo kit's own Yahoo pulls (fetch_us_overview.py / fetch_asia_overview.py): the ticker lists are
the kit's, unchanged, and fetched in one chunked yfinance batch (period 4mo) through ingest/prices._download.

Row fields: last, r1/r5/r20 (close-to-close over 1/5/20 of the ticker's own sessions), rel1/rel5/rel20 (minus the
same-window return of the reference: ^GSPC on the US run, the ticker's own market benchmark on the Asia run),
off_hi (last / 3-month closing high - 1), volr (latest volume / prior 20-session average), has_close_on_asof
(false when Yahoo has not yet published the session expected for that ticker: its returns are then null, never
stale). ^TNX / ^FVX also carry d1_bp / d5_bp / d20_bp. A failed download writes the block with "error" and no rows.
"""
from __future__ import annotations

import pandas as pd

from ..config import log

US_GROUPS = {
    "bench": "^GSPC ^IXIC ^DJI ^RUT ^VIX RSP QQQ ^TNX ^FVX TLT HYG DX-Y.NYB CL=F GC=F",
    "sector_etf": "XLK XLC XLY XLP XLV XLF XLI XLE XLB XLU XLRE",
    "industry_etf": "SOXX SMH IGV XBI ITA URA KRE XHB IYT ARKK GLD SLV COPX XOP IBIT BOTZ ARKX QTUM",
    "mag7": "AAPL MSFT NVDA AMZN GOOGL META TSLA AVGO",
    "adr": "TSM SKHY UMC ASX BABA PDD JD BIDU NTES YUMC TCOM LI NIO XPEV SONY TM MUFG SMFG KB SHG CPNG SE GRAB",
    "country": "EWJ EWY EWT FXI EEM",
}
ASIA_GROUPS = {
    "bench": "^KS11 ^KQ11 ^N225 1306.T ^TWII ^HSI 3033.HK 510300.SS ^GSPC ES=F NQ=F ^VIX ^TNX CL=F GC=F",
    "fx": "KRW=X JPY=X TWD=X CNY=X HKD=X DX-Y.NYB",
    "kr": "005930.KS 000660.KS 373220.KS 035420.KS 207940.KS 005380.KS 105560.KS 012450.KS",
    "jp": "7203.T 6758.T 9984.T 8035.T 6857.T 6501.T 8306.T 7011.T 6098.T 4063.T",
    "tw": "2330.TW 2317.TW 2454.TW 2308.TW 2382.TW 3711.TW 2881.TW 1303.TW",
    "hk": "0700.HK 9988.HK 3690.HK 1810.HK 0005.HK 1299.HK 0981.HK 9618.HK 2015.HK 1024.HK",
}
YIELDS = ("^TNX", "^FVX")


def groups_for(run: str) -> dict[str, list[str]]:
    return {k: v.split() for k, v in (US_GROUPS if run == "us" else ASIA_GROUPS).items()}


def home_calendar(t: str) -> str | None:
    """Exchange calendar whose last closed session a ticker should have a bar for; None = trades around the clock."""
    if t.endswith("=X") or t.endswith("=F") or t == "DX-Y.NYB":
        return None
    if t.endswith((".KS", ".KQ")) or t in ("^KS11", "^KQ11"):
        return "XKRX"
    if t.endswith(".T") or t == "^N225":
        return "XTKS"
    if t.endswith((".TW", ".TWO")) or t == "^TWII":
        return "XTAI"
    if t.endswith(".HK") or t == "^HSI":
        return "XHKG"
    if t.endswith((".SS", ".SZ")):
        return "XSHG"
    return "XNYS"


ASIA_REF = {"XKRX": "^KS11", "XTKS": "1306.T", "XTAI": "^TWII", "XHKG": "^HSI", "XSHG": "510300.SS", "XNYS": "^GSPC"}


def _last_closed(cal_code: str, now: pd.Timestamp) -> pd.Timestamp:
    import exchange_calendars as xc
    cal = xc.get_calendar(cal_code)
    s = cal.date_to_session(now.tz_convert(cal.tz).normalize().tz_localize(None), direction="previous")
    while cal.session_close(s) > now:
        s = cal.previous_session(s)
    return pd.Timestamp(s).tz_localize(None) if pd.Timestamp(s).tzinfo else pd.Timestamp(s)


def _r(s: pd.Series, n: int):
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1) if len(s) > n and s.iloc[-1 - n] > 0 else None


def compute_overview(long: pd.DataFrame, run: str, now: pd.Timestamp | None = None) -> dict:
    """Pure computation from a long [date, ticker, close, volume] frame (testable without the network)."""
    now = now or pd.Timestamp.now(tz="UTC")
    groups = groups_for(run)
    tickers = list(dict.fromkeys(sum(groups.values(), [])))
    close = long.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    vol = long.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex_like(close)
    expected: dict[str, pd.Timestamp] = {}
    cache: dict[str, pd.Timestamp] = {}
    for t in tickers:
        cal = home_calendar(t)
        if cal is not None:
            if cal not in cache:
                cache[cal] = _last_closed(cal, now)
            expected[t] = cache[cal]
    series = {t: close[t].dropna() for t in tickers if t in close.columns}
    rows, as_of = {}, None
    for t in tickers:
        s = series.get(t)
        if s is None or s.empty:
            rows[t] = {"last": None, "r1": None, "r5": None, "r20": None, "rel1": None, "rel5": None, "rel20": None,
                       "off_hi": None, "volr": None, "has_close_on_asof": False, "last_date": None}
            continue
        last_date = s.index[-1]
        exp = expected.get(t)
        # around-the-clock instruments (FX, futures): fresh if the last bar is within four days of now
        has = (last_date >= exp) if exp is not None else (last_date >= now.tz_localize(None).normalize() - pd.Timedelta(days=4))
        hi = s[s.index >= last_date - pd.Timedelta(days=92)].max()
        v = vol[t].reindex(s.index) if t in vol.columns else None
        volr = None
        if v is not None and len(v.dropna()) > 20:
            prior = v.iloc[-21:-1].mean()
            volr = float(v.iloc[-1] / prior) if prior and prior > 0 and pd.notna(v.iloc[-1]) else None
        row = {"last": round(float(s.iloc[-1]), 4), "r1": _r(s, 1), "r5": _r(s, 5), "r20": _r(s, 20),
               "off_hi": float(s.iloc[-1] / hi - 1) if hi and hi > 0 else None, "volr": volr,
               "has_close_on_asof": bool(has), "last_date": last_date.strftime("%Y-%m-%d")}
        if t in YIELDS:
            for n in (1, 5, 20):
                row[f"d{n}_bp"] = round(float((s.iloc[-1] - s.iloc[-1 - n]) * 100), 1) if len(s) > n else None
        if not has:  # never report a stale session as today's move
            for k in ("r1", "r5", "r20", "off_hi", "volr", "d1_bp", "d5_bp", "d20_bp"):
                if k in row:
                    row[k] = None
        rows[t] = row
        if has and exp is not None and (as_of is None or exp > as_of):
            as_of = exp
    # relative returns, over the same sessions of the reference series
    for t, row in rows.items():
        if run == "us":
            ref = "^GSPC"
        else:
            cal = home_calendar(t)
            ref = ASIA_REF.get(cal) if cal is not None else None
        if t in YIELDS or ref is None or row["r1"] is None or ref not in rows or rows[ref]["r1"] is None:
            continue
        for n in (1, 5, 20):
            a, b = row[f"r{n}"], rows[ref][f"r{n}"]
            row[f"rel{n}"] = None if a is None or b is None else round(a - b, 6)
    for row in rows.values():
        for k in ("r1", "r5", "r20", "off_hi", "volr"):
            if row.get(k) is not None:
                row[k] = round(row[k], 6)
    lead = "XNYS" if run == "us" else "XHKG"
    as_of = cache.get(lead, as_of)
    return {"as_of": as_of.strftime("%Y-%m-%d") if as_of is not None else None, "groups": groups, "rows": rows,
            "reference": "^GSPC" if run == "us" else "own market benchmark (^KS11, 1306.T, ^TWII, ^HSI, 510300.SS; ^GSPC for US)"}


def build_overview(run: str) -> dict:
    """Fetch and compute; never raises."""
    from .prices import _download
    groups = groups_for(run)
    tickers = list(dict.fromkeys(sum(groups.values(), [])))
    try:
        long = _download(tickers, None, "4mo")
        if long.empty:
            raise RuntimeError("empty download")
        out = compute_overview(long, run)
        missing = [t for t, r in out["rows"].items() if r["last"] is None]
        if missing:
            out["missing"] = missing
        log.info("%s_overview: %d/%d tickers, %d without today's close", run, len(tickers) - len(missing), len(tickers),
                 sum(not r["has_close_on_asof"] for r in out["rows"].values()))
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("%s_overview failed: %s", run, repr(e)[:200])
        return {"as_of": None, "groups": groups, "rows": {}, "error": repr(e)[:200]}
