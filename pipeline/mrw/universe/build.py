"""Universe builders: one CSV per market in data/universe/, plus a ticker metadata cache.

Columns of data/universe/{MKT}.csv:
  ticker, name, market, sector_local, sector, mcap_local, shares, source_index
"""
from __future__ import annotations

import datetime as dt
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from ..config import (MARKETS, MOBILE_UA, THEMES, UNIVERSE_DIR, OUTPUT_DIR, harmonise_sector, log, write_json)
from ..http import get

WIKI_UA = "MarketRotationWatch/0.1 (personal research tool; https://github.com) python-requests"
META_CACHE = UNIVERSE_DIR / "meta_cache.csv"
META_MAX_AGE_DAYS = 30


# ----------------------------------------------------------------------------- metadata cache
def load_meta_cache() -> pd.DataFrame:
    if META_CACHE.exists():
        df = pd.read_csv(META_CACHE, dtype={"ticker": str})
        return df.set_index("ticker")
    return pd.DataFrame(columns=["name", "sector_yahoo", "industry_yahoo", "mcap", "shares", "currency", "fetched"]).set_index(
        pd.Index([], name="ticker"))


def _fetch_info(ticker: str) -> dict:
    """One quoteSummary call with rate-limit backoff (Yahoo throttles this endpoint hard)."""
    import time
    from yfinance.exceptions import YFRateLimitError
    for attempt in range(4):
        try:
            info = yf.Ticker(ticker).info or {}
            break
        except YFRateLimitError:
            wait = 45 * (attempt + 1)
            log.warning("Yahoo rate limit on %s, sleeping %ds", ticker, wait)
            time.sleep(wait)
            info = None
        except Exception as e:  # noqa: BLE001
            return {"ticker": ticker, "error": repr(e)[:120]}
    if info is None:
        return {"ticker": ticker, "error": "rate-limited"}
    if not info or (info.get("quoteType") is None and info.get("regularMarketPrice") is None):
        return {"ticker": ticker, "error": "empty"}
    return {
        "ticker": ticker,
        "name": info.get("shortName") or info.get("longName"),
        "sector_yahoo": info.get("sector"),
        "industry_yahoo": info.get("industry"),
        "mcap": info.get("marketCap"),
        "shares": info.get("sharesOutstanding"),
        "currency": info.get("currency"),
        "fetched": dt.date.today().isoformat(),
    }


def _flush_meta(cache: pd.DataFrame, rows: list[dict]) -> None:
    if rows:
        new = pd.DataFrame(rows).set_index("ticker")
        pd.concat([cache.drop(index=new.index, errors="ignore"), new]).to_csv(META_CACHE)


def refresh_meta(tickers: list[str], force: bool = False, workers: int = 1, pace: float = 0.8) -> pd.DataFrame:
    """Fetch Yahoo metadata for tickers missing from the cache or older than META_MAX_AGE_DAYS."""
    cache = load_meta_cache()
    today = dt.date.today()
    todo = []
    for t in dict.fromkeys(tickers):
        if force or t not in cache.index:
            todo.append(t)
        else:
            try:
                age = (today - dt.date.fromisoformat(str(cache.loc[t, "fetched"]))).days
            except Exception:  # noqa: BLE001
                age = 999
            if age > META_MAX_AGE_DAYS or pd.isna(cache.loc[t, "mcap"]) or pd.isna(cache.loc[t, "sector_yahoo"]):
                todo.append(t)
    if todo:
        log.info("fetching Yahoo metadata for %d tickers", len(todo))
        rows, errors = [], []
        import time
        for i, t in enumerate(todo, 1):
            r = _fetch_info(t)
            if "error" in r:
                errors.append(r)
            else:
                rows.append(r)
            if i % 50 == 0:
                log.info("  metadata %d/%d", i, len(todo))
                _flush_meta(cache, rows)
            time.sleep(pace)
        if rows:
            new = pd.DataFrame(rows).set_index("ticker")
            cache = pd.concat([cache.drop(index=new.index, errors="ignore"), new])
        if errors:
            log.warning("metadata unresolved for %d tickers: %s", len(errors), [e["ticker"] for e in errors][:20])
        cache.to_csv(META_CACHE)
    return cache


# ----------------------------------------------------------------------------- per-market lists
def _list_sp500() -> pd.DataFrame:
    html = get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", ua=WIKI_UA, pause=1.0, retries=4).text
    tables = pd.read_html(io.StringIO(html))
    t = next(x for x in tables if "Symbol" in x.columns and "GICS Sector" in x.columns)
    df = pd.DataFrame({
        "ticker": t["Symbol"].str.replace(".", "-", regex=False).str.strip(),
        "name": t["Security"],
        "sector_local": t["GICS Sector"],
        "source_index": "SP500",
    })
    assert 480 <= len(df) <= 520, f"S&P 500 table looks wrong: {len(df)} rows"
    return df


def _list_ndx() -> pd.DataFrame:
    # components table: Ticker / Company / ICB Industry / ICB Subsector (no GICS column, so Nasdaq-100-only
    # names take Yahoo's sector in build_all)
    html = get("https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies", ua=WIKI_UA, pause=1.0, retries=4).text
    tables = pd.read_html(io.StringIO(html))
    t = next((x for x in tables if any(c in x.columns for c in ("Ticker", "Symbol")) and 90 <= len(x) <= 110), None)
    if t is None:
        raise RuntimeError(f"no Nasdaq-100 components table among {len(tables)} tables: "
                           f"{[(list(x.columns)[:4], len(x)) for x in tables][:8]}")
    tick_col = "Ticker" if "Ticker" in t.columns else "Symbol"
    name_col = next((c for c in ("Company", "Security", "Name") if c in t.columns), tick_col)
    sec_col = next((c for c in t.columns if str(c).startswith("GICS Sector") or str(c) == "Sector"), None)
    df = pd.DataFrame({
        "ticker": t[tick_col].astype(str).str.replace(".", "-", regex=False).str.strip(),
        "name": t[name_col],
        "sector_local": t[sec_col] if sec_col is not None else None,
        "source_index": "NDX",
    })
    assert 95 <= len(df) <= 110, f"Nasdaq-100 table looks wrong: {len(df)} rows"
    return df


def list_us() -> pd.DataFrame:
    """S&P 500 ∪ Nasdaq-100, union by ticker; the GICS sector comes from the S&P table first, then the Nasdaq-100
    table, then (in build_all) Yahoo's sector for names neither table tags with a GICS sector."""
    sp = _list_sp500()
    try:
        ndx = _list_ndx()
    except Exception as e:  # noqa: BLE001
        log.warning("Nasdaq-100 list failed (%s) — keeping previous NDX-only names", e)
        prev = UNIVERSE_DIR / "US.csv"
        ndx = pd.DataFrame(columns=sp.columns)
        if prev.exists():
            old = pd.read_csv(prev, dtype={"ticker": str})
            ndx = old.loc[old["source_index"].astype(str).str.contains("NDX"), ["ticker", "name", "sector_local", "source_index"]]
    both = set(sp["ticker"]) & set(ndx["ticker"])
    sp.loc[sp["ticker"].isin(both), "source_index"] = "SP500+NDX"
    ndx_sector = ndx.set_index("ticker")["sector_local"]
    sp["sector_local"] = sp["sector_local"].where(sp["sector_local"].notna(), sp["ticker"].map(ndx_sector))
    df = pd.concat([sp, ndx[~ndx["ticker"].isin(both)].assign(source_index="NDX")], ignore_index=True)
    df = df.drop_duplicates("ticker", keep="first").reset_index(drop=True)
    log.info("US universe: %d S&P 500 + %d Nasdaq-100-only = %d", len(sp), len(df) - len(sp), len(df))
    assert 500 <= len(df) <= 620, f"S&P 500 ∪ Nasdaq-100 looks wrong: {len(df)} rows"
    return df


def list_kr() -> pd.DataFrame:
    rows = []
    for page in range(1, 8):
        j = get(f"https://m.stock.naver.com/api/index/KPI200/enrollStocks?page={page}&pageSize=50",
                ua=MOBILE_UA, expect_json=True, pause=0.3)
        if not j:
            break
        rows.extend(j)
        if len(j) < 50:
            break
    df = pd.DataFrame({
        "ticker": [r["itemCode"] + ".KS" for r in rows],
        "name": [r["stockName"] for r in rows],
        "sector_local": None,
        "mcap_naver_100m": [float(str(r.get("marketValue", "0")).replace(",", "") or 0) for r in rows],
        "source_index": "KOSPI200",
    })
    assert 180 <= len(df) <= 210, f"KOSPI200 list looks wrong: {len(df)} rows"
    return df


def _wiki_hk(page: str, index_name: str) -> pd.DataFrame:
    html = get(f"https://en.wikipedia.org/wiki/{page}", ua=WIKI_UA, pause=8.0, retries=3).text
    tables = pd.read_html(io.StringIO(html))
    cands = [t for t in tables if any(str(c).lower().startswith("ticker") for c in t.columns)]
    t = max(cands, key=len)
    tick_col = next(c for c in t.columns if str(c).lower().startswith("ticker"))
    name_col = next((c for c in t.columns if str(c).lower() in ("name", "company", "company name")), t.columns[1])
    codes = t[tick_col].astype(str).str.extract(r"(\d+)")[0]
    df = pd.DataFrame({
        "ticker": codes.dropna().astype(int).map(lambda c: f"{c:04d}.HK"),
        "name": t[name_col].astype(str),
        "sector_local": t[next((c for c in t.columns if "sub" in str(c).lower() or "industry" in str(c).lower()), tick_col)].astype(str)
        if any("sub" in str(c).lower() or "industry" in str(c).lower() for c in t.columns) else None,
        "source_index": index_name,
    }).dropna(subset=["ticker"])
    return df


# Hang Seng TECH has no Wikipedia constituents table; static seed (Oct 2026), reviewed monthly.
STATIC_HSTECH = ["0700.HK", "9988.HK", "3690.HK", "9618.HK", "1024.HK", "9999.HK", "1810.HK", "1211.HK", "9868.HK",
                 "9866.HK", "2015.HK", "0981.HK", "1347.HK", "0020.HK", "3888.HK", "0268.HK", "9660.HK", "2382.HK",
                 "0285.HK", "9698.HK", "6690.HK", "0241.HK", "6060.HK", "0780.HK", "9626.HK", "9888.HK", "9961.HK",
                 "0772.HK", "6618.HK", "0992.HK", "6969.HK", "2018.HK", "9880.HK", "2013.HK", "0763.HK", "9901.HK"]


def list_hk() -> pd.DataFrame:
    parts = []
    for page, name in [("Hang_Seng_Index", "HSI"), ("Hang_Seng_China_Enterprises_Index", "HSCEI")]:
        try:
            parts.append(_wiki_hk(page, name))
        except Exception as e:  # noqa: BLE001
            log.warning("HK list %s failed: %s", name, e)
    parts.append(pd.DataFrame({"ticker": STATIC_HSTECH, "name": None, "sector_local": None, "source_index": "HSTECH_static"}))
    prev = UNIVERSE_DIR / "HK.csv"
    if prev.exists():  # keep last good union so a failed Wikipedia fetch never shrinks the universe
        old = pd.read_csv(prev, dtype={"ticker": str})
        parts.append(old[["ticker", "name", "sector_local", "source_index"]])
    df = pd.concat(parts).drop_duplicates("ticker", keep="first").reset_index(drop=True)
    df["sector_local"] = None  # use Yahoo sector for harmonisation
    assert len(df) >= 60, f"HK list looks wrong: {len(df)} rows"
    return df


def list_jp() -> pd.DataFrame:
    url = "https://www.jpx.co.jp/english/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_e.xlsx"
    r = get(url, timeout=90)
    x = pd.read_excel(io.BytesIO(r.content))
    size = x["Size Code (New Index Series)"].astype(str)
    sel = x[size.isin(["1", "2", "4"])].copy()  # Core30 + Large70 + Mid400 = TOPIX 500
    df = pd.DataFrame({
        "ticker": sel["Local Code"].astype(str).str.strip() + ".T",
        "name": sel["Name (English)"],
        "sector_local": sel["17 Sector(name)"].astype(str).str.strip(),
        "source_index": "TOPIX500",
    })
    assert 450 <= len(df) <= 520, f"TOPIX500 list looks wrong: {len(df)} rows"
    return df


def _twse_last_trading_day() -> str:
    import exchange_calendars as xc
    cal = xc.get_calendar("XTAI")
    d = pd.Timestamp.today(tz="Asia/Taipei").normalize().tz_localize(None)
    if cal.is_session(d) and pd.Timestamp.now(tz="Asia/Taipei").hour < 15:
        d = cal.previous_session(d)
    while not cal.is_session(d):
        d = cal.previous_session(d)
    return d.strftime("%Y%m%d")


def list_tw(top_n: int = 150, pre_n: int = 320) -> pd.DataFrame:
    d = _twse_last_trading_day()
    j = get("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
            params={"date": d, "type": "ALLBUT0999", "response": "json"},
            headers={"Referer": "https://www.twse.com.tw/zh/trading/historical/mi-index.html"},
            expect_json=True, timeout=60, pause=1.0)
    tbl = None
    for t in j.get("tables", []):
        if t.get("fields") and "證券代號" in t["fields"] and "成交金額" in t["fields"]:
            tbl = t
    if tbl is None:
        raise RuntimeError("TWSE MI_INDEX: stock table not found")
    df = pd.DataFrame(tbl["data"], columns=tbl["fields"])
    df = df[df["證券代號"].astype(str).str.fullmatch(r"\d{4}")]
    df["turnover"] = pd.to_numeric(df["成交金額"].str.replace(",", ""), errors="coerce")
    df = df.sort_values("turnover", ascending=False).head(pre_n)
    out = pd.DataFrame({
        "ticker": df["證券代號"].astype(str) + ".TW",
        "name": df["證券名稱"].astype(str).str.strip(),
        "sector_local": None,
        "source_index": "TWSE_TOP150_MCAP",
    })
    meta = refresh_meta(out["ticker"].tolist())
    out["mcap_local"] = out["ticker"].map(meta["mcap"])
    out = out.dropna(subset=["mcap_local"]).sort_values("mcap_local", ascending=False).head(top_n)
    return out.drop(columns=["mcap_local"]).reset_index(drop=True)


BUILDERS = {"US": list_us, "KR": list_kr, "HK": list_hk, "JP": list_jp, "TW": list_tw}


# ----------------------------------------------------------------------------- assemble
def theme_tickers() -> list[str]:
    out = []
    for th in THEMES.values():
        for mkt, members in th["members"].items():
            out.extend(members)
    return list(dict.fromkeys(out))


def build_all(markets: list[str] | None = None, force_meta: bool = False) -> dict:
    report = {"built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "markets": {}, "themes": {}}
    frames = {}
    for mkt in markets or list(MARKETS):
        try:
            df = BUILDERS[mkt]()
            df["market"] = mkt
            frames[mkt] = df
            log.info("%s: %d constituents", mkt, len(df))
        except Exception as e:  # noqa: BLE001
            log.error("universe build failed for %s: %s — keeping previous file", mkt, e)
            report["markets"][mkt] = {"error": str(e)[:300]}
            prev = UNIVERSE_DIR / f"{mkt}.csv"
            if prev.exists():
                frames[mkt] = pd.read_csv(prev, dtype={"ticker": str})

    all_tickers = list(dict.fromkeys(sum([f["ticker"].tolist() for f in frames.values()], []) + theme_tickers()))
    meta = refresh_meta(all_tickers, force=force_meta)

    for mkt, df in frames.items():
        scheme = MARKETS[mkt]["sector_scheme"]
        df = df.copy()
        df["name"] = df["name"].where(df["name"].notna(), df["ticker"].map(meta["name"]))
        if scheme == "YAHOO":
            df["sector_local"] = df["ticker"].map(meta["industry_yahoo"])
            df["sector"] = df["ticker"].map(meta["sector_yahoo"]).map(lambda s: harmonise_sector("YAHOO", s))
        else:
            df["sector"] = df["sector_local"].map(lambda s: harmonise_sector(scheme, s))
            # names without a usable local tag (e.g. Nasdaq-100-only listings) fall back to Yahoo's sector
            df["sector"] = df["sector"].fillna(df["ticker"].map(meta["sector_yahoo"]).map(lambda s: harmonise_sector("YAHOO", s)))
        df["mcap_local"] = df["ticker"].map(meta["mcap"])
        df["shares"] = df["ticker"].map(meta["shares"])
        if mkt == "KR" and "mcap_naver_100m" in df.columns:
            df["mcap_local"] = df["mcap_local"].fillna(df["mcap_naver_100m"] * 1e8)
            df = df.drop(columns=["mcap_naver_100m"])
        missing_sector = int(df["sector"].isna().sum())
        df["sector"] = df["sector"].fillna("Unclassified")
        cols = ["ticker", "name", "market", "sector_local", "sector", "mcap_local", "shares", "source_index"]
        df[cols].to_csv(UNIVERSE_DIR / f"{mkt}.csv", index=False)
        report["markets"][mkt] = {"count": int(len(df)), "missing_sector": missing_sector,
                                  "missing_mcap": int(df["mcap_local"].isna().sum())}

    # theme validation
    for key, th in THEMES.items():
        unresolved = [t for m in th["members"].values() for t in m if t not in meta.index]
        report["themes"][key] = {"members": sum(len(m) for m in th["members"].values()), "unresolved": unresolved}
        if unresolved:
            log.warning("theme %s unresolved tickers: %s", key, unresolved)

    write_json(OUTPUT_DIR / "universe_report.json", report)
    return report


def load_universe(mkt: str) -> pd.DataFrame:
    return pd.read_csv(UNIVERSE_DIR / f"{mkt}.csv", dtype={"ticker": str})


def load_all_universes() -> pd.DataFrame:
    return pd.concat([load_universe(m) for m in MARKETS if (UNIVERSE_DIR / f"{m}.csv").exists()], ignore_index=True)
