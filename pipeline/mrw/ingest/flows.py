"""Investor-type flow ingestion for Korea (Naver), Hong Kong (HKEX Southbound), Taiwan (TWSE)
and Japan (JPX weekly). Each is stored under data/flows/{MKT}/ as monthly parquet partitions.

All ingesters are best-effort: a failure logs a warning and leaves the last good data in place.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import FLOWS_DIR, MOBILE_UA, THEMES, log
from ..http import get
from ..universe.build import load_universe


# ----------------------------------------------------------------------------- storage helpers
def _load(mkt: str) -> pd.DataFrame:
    d = FLOWS_DIR / mkt
    files = sorted(d.glob("*.parquet")) if d.exists() else []
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _save(mkt: str, df: pd.DataFrame, keys: list[str]) -> None:
    d = FLOWS_DIR / mkt
    d.mkdir(parents=True, exist_ok=True)
    df = df.drop_duplicates(keys, keep="last").sort_values(keys)
    df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    for m, part in df.groupby("month"):
        part.drop(columns=["month"]).reset_index(drop=True).to_parquet(d / f"{m}.parquet", index=False)


def load_flows(mkt: str) -> pd.DataFrame:
    df = _load(mkt)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def _kr_tickers() -> list[str]:
    t = load_universe("KR")["ticker"].tolist()
    for th in THEMES.values():
        t += th["members"].get("KR", [])
    return list(dict.fromkeys(t))


def _tw_tickers() -> list[str]:
    t = load_universe("TW")["ticker"].tolist()
    for th in THEMES.values():
        t += th["members"].get("TW", [])
    return list(dict.fromkeys(t))


# ----------------------------------------------------------------------------- Korea (Naver)
def _naver_num(s) -> float:
    try:
        return float(str(s).replace(",", "").replace("+", ""))
    except ValueError:
        return float("nan")


def _kr_fetch_one(ticker: str, pages: int) -> list[dict]:
    """Naver's trend API ignores `page`; paging works by passing `bizdate` = oldest date seen so far."""
    code = ticker.split(".")[0]
    rows: list[dict] = []
    bizdate = None
    for _ in range(pages):
        url = f"https://m.stock.naver.com/api/stock/{code}/trend?pageSize=50" + (f"&bizdate={bizdate}" if bizdate else "")
        try:
            j = get(url, ua=MOBILE_UA, expect_json=True, pause=0.15, retries=2)
        except Exception as e:  # noqa: BLE001
            log.warning("KR flows %s failed: %s", ticker, repr(e)[:80])
            break
        if not j:
            break
        for r in j:
            close = _naver_num(r.get("closePrice"))
            rows.append({
                "date": pd.Timestamp(r["bizdate"]), "ticker": ticker,
                "foreign_qty": _naver_num(r.get("foreignerPureBuyQuant")),
                "inst_qty": _naver_num(r.get("organPureBuyQuant")),
                "retail_qty": _naver_num(r.get("individualPureBuyQuant")),
                "close": close,
                "foreign_hold_pct": _naver_num(str(r.get("foreignerHoldRatio", "")).replace("%", "")),
            })
        if len(j) < 50:
            break
        bizdate = j[-1]["bizdate"]
    return rows


def update_kr(backfill_pages: int = 5, workers: int = 4) -> dict:
    """Per-stock daily net buying by investor type. Values in KRW = qty × close."""
    existing = load_flows("KR")
    tickers = _kr_tickers()
    pages = backfill_pages if existing.empty else 1
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(lambda t: _kr_fetch_one(t, pages), tickers):
            rows.extend(res)
    if not rows:
        return {"ok": False, "reason": "no rows"}
    new = pd.DataFrame(rows)
    for k in ("foreign", "inst", "retail"):
        new[f"{k}_val"] = new[f"{k}_qty"] * new["close"]
    merged = pd.concat([existing, new], ignore_index=True) if not existing.empty else new
    _save("KR", merged, ["date", "ticker"])
    return {"ok": True, "tickers": int(new["ticker"].nunique()), "last_date": str(new["date"].max().date()), "rows": len(new)}


# ----------------------------------------------------------------------------- Hong Kong (HKEX Southbound)
def _hk_parse(text: str, date: pd.Timestamp) -> list[dict]:
    body = text.split("=", 1)[1].strip().rstrip(";")
    j = json.loads(body)
    rows = []
    for blk in j:
        market = blk.get("market", "")
        if "Southbound" not in market:
            continue
        channel = "SSE" if market.startswith("SSE") else "SZSE"
        if not blk.get("tradingDay", 1):
            continue
        for c in blk.get("content", []):
            tbl = c.get("table", {})
            schema = [s for s in tbl.get("schema", [[]])[0]]
            trs = tbl.get("tr", [])
            if schema and schema[0] == "Total Turnover":
                vals = [float(str(tr["td"][0][0]).replace(",", "")) for tr in trs]
                d = dict(zip(schema, vals))
                rows.append({"date": date, "channel": channel, "ticker": "TOTAL", "name": "TOTAL",
                             "buy": d.get("Buy Turnover", float("nan")) * 1e6,  # HKD million -> HKD
                             "sell": d.get("Sell Turnover", float("nan")) * 1e6})
            elif schema and schema[0] == "Rank":
                for tr in trs:
                    td = tr["td"][0]
                    code = int(td[1])
                    rows.append({"date": date, "channel": channel, "ticker": f"{code:04d}.HK", "name": td[2],
                                 "buy": float(td[3].replace(",", "")), "sell": float(td[4].replace(",", ""))})
    return rows


def update_hk(backfill_days: int = 120) -> dict:
    import exchange_calendars as xc
    cal = xc.get_calendar("XHKG")
    existing = load_flows("HK")
    today = pd.Timestamp.today(tz="Asia/Hong_Kong").normalize().tz_localize(None)
    if pd.Timestamp.now(tz="Asia/Hong_Kong").hour < 17:
        today = today - pd.Timedelta(days=1)
    sessions = cal.sessions_in_range(today - pd.Timedelta(days=backfill_days * 2), today)
    sessions = list(sessions[-backfill_days:])
    have = set(existing["date"].unique()) if not existing.empty else set()
    todo = [s for s in sessions if s.tz_localize(None) not in have][-backfill_days:]
    if not existing.empty:
        todo = [s for s in todo if s >= existing["date"].max() - pd.Timedelta(days=5)] or todo[-3:]
    rows, fetched = [], 0
    for s in todo:
        d = s.strftime("%Y%m%d")
        try:
            r = get(f"https://www.hkex.com.hk/eng/csm/DailyStat/data_tab_daily_{d}e.js", pause=0.4, retries=2)
            if "tabData" not in r.text:
                continue
            rows.extend(_hk_parse(r.text, pd.Timestamp(s.tz_localize(None))))
            fetched += 1
        except Exception as e:  # noqa: BLE001
            log.warning("HK southbound %s failed: %s", d, repr(e)[:80])
    if not rows:
        return {"ok": not existing.empty, "days_fetched": 0, "reason": "no new day published yet",
                "last_date": str(existing["date"].max().date()) if not existing.empty else None}
    new = pd.DataFrame(rows)
    new["net"] = new["buy"] - new["sell"]
    merged = pd.concat([existing, new], ignore_index=True) if not existing.empty else new
    _save("HK", merged, ["date", "channel", "ticker"])
    return {"ok": True, "days_fetched": fetched, "fetched_dates": sorted({str(x.date()) for x in pd.to_datetime(new["date"])}),
            "last_date": str(pd.to_datetime(merged["date"]).max().date())}


# ----------------------------------------------------------------------------- Taiwan (TWSE T86)
def _tw_num(s) -> float:
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return float("nan")


def update_tw(backfill_days: int = 60) -> dict:
    import exchange_calendars as xc
    cal = xc.get_calendar("XTAI")
    existing = load_flows("TW")
    keep = set(_tw_tickers())
    today = pd.Timestamp.today(tz="Asia/Taipei").normalize().tz_localize(None)
    if pd.Timestamp.now(tz="Asia/Taipei").hour < 16:
        today = today - pd.Timedelta(days=1)
    sessions = list(cal.sessions_in_range(today - pd.Timedelta(days=backfill_days * 2), today))[-backfill_days:]
    have = set(existing["date"].unique()) if not existing.empty else set()
    todo = [s for s in sessions if s.tz_localize(None) not in have]
    if not existing.empty:
        todo = [s for s in todo if s >= existing["date"].max() - pd.Timedelta(days=5)] or todo[-3:]
    rows, fetched = [], 0
    for s in todo:
        d = s.strftime("%Y%m%d")
        try:
            j = get("https://www.twse.com.tw/rwd/zh/fund/T86", params={"date": d, "selectType": "ALL", "response": "json"},
                    headers={"Referer": "https://www.twse.com.tw/zh/trading/foreign/t86.html"}, expect_json=True,
                    pause=2.5, retries=2, timeout=60)
        except Exception as e:  # noqa: BLE001
            log.warning("TW T86 %s failed: %s", d, repr(e)[:80])
            continue
        if j.get("stat") != "OK" or "data" not in j:
            continue
        f = j["fields"]
        ix = {name: i for i, name in enumerate(f)}
        col_for = lambda key: ix[key] if key in ix else next((ix[c] for c in f if key in c), None)  # noqa: E731
        i_code, i_foreign, i_trust, i_dealer, i_total = (ix["證券代號"], col_for("外陸資買賣超股數"),
                                                        col_for("投信買賣超股數"), col_for("自營商買賣超股數"),
                                                        col_for("三大法人買賣超股數"))
        for row in j["data"]:
            t = str(row[i_code]).strip() + ".TW"
            if t not in keep:
                continue
            rows.append({"date": pd.Timestamp(s.tz_localize(None)), "ticker": t,
                         "foreign_qty": _tw_num(row[i_foreign]), "trust_qty": _tw_num(row[i_trust]),
                         "dealer_qty": _tw_num(row[i_dealer]), "total_qty": _tw_num(row[i_total])})
        fetched += 1
    if not rows:
        return {"ok": not existing.empty, "days_fetched": 0, "reason": "no new day published yet",
                "last_date": str(existing["date"].max().date()) if not existing.empty else None}
    new = pd.DataFrame(rows)
    merged = pd.concat([existing, new], ignore_index=True) if not existing.empty else new
    _save("TW", merged, ["date", "ticker"])
    # last_date = newest session now stored (a run that only back-fills old gaps used to report the gap's date)
    return {"ok": True, "days_fetched": fetched, "fetched_dates": sorted({str(x.date()) for x in pd.to_datetime(new["date"])}),
            "last_date": str(pd.to_datetime(merged["date"]).max().date())}


# ----------------------------------------------------------------------------- Japan (JPX weekly)
JPX_INVESTORS = {"Foreigners": "foreigners", "Individuals": "individuals", "Investment Tr": "investment_trusts",
                 "Securities Co": "securities_cos", "Business Cos": "business_cos", "Life & Non-L": "insurers",
                 "City & Regi": "banks", "Trust Bank": "trust_banks", "Proprietary": "proprietary"}


def _jpx_parse(content: bytes) -> dict | None:
    x = pd.read_excel(io.BytesIO(content), header=None)
    # locate TSE Prime "Value" row
    prime_row = None
    for i in range(len(x)):
        if any("Prime" in str(v) for v in x.iloc[i].tolist()):
            prime_row = i
            break
    if prime_row is None:
        return None
    val_row = prime_row + 1 if "Value" in str(x.iloc[prime_row + 1, 2]) else prime_row
    week = str(x.iloc[prime_row, 0])
    out = {"week": week}
    header_rows = range(0, prime_row)
    for label, key in JPX_INVESTORS.items():
        col = None
        for r in header_rows:
            for c, v in enumerate(x.iloc[r].tolist()):
                if label in str(v):
                    col = c
                    break
            if col is not None:
                break
        if col is None:
            continue
        # group layout: Sales, Purchases, Balance, Total
        try:
            out[key] = float(x.iloc[val_row, col + 2]) * 1e3  # thousand JPY -> JPY
        except (ValueError, TypeError):
            pass
    return out


def update_jp(max_weeks: int = 26) -> dict:
    existing = load_flows("JP")
    try:
        html = get("https://www.jpx.co.jp/english/markets/statistics-equities/investor-type/index.html", timeout=60).text
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": repr(e)[:100]}
    links = re.findall(r'href="(/english/markets/statistics-equities/investor-type/[^"]*stock_1_w_(\d{8})_(\d{8})\.xlsx)"', html)
    have = set(existing["week_end"].astype(str)) if not existing.empty else set()
    rows = []
    for path, start, end in links[:max_weeks]:
        if end in have:
            continue
        try:
            r = get("https://www.jpx.co.jp" + path, pause=0.5, timeout=60)
            parsed = _jpx_parse(r.content)
        except Exception as e:  # noqa: BLE001
            log.warning("JPX weekly %s failed: %s", end, repr(e)[:80])
            continue
        if parsed:
            parsed.update({"week_start": start, "week_end": end, "date": pd.Timestamp(end)})
            rows.append(parsed)
    if not rows:
        return {"ok": True, "new_weeks": 0, "last_week": max(have) if have else None}
    new = pd.DataFrame(rows)
    merged = pd.concat([existing, new], ignore_index=True) if not existing.empty else new
    _save("JP", merged, ["week_end"])
    return {"ok": True, "new_weeks": len(new), "last_week": str(new["week_end"].max())}


def update_all() -> dict:
    report = {}
    for name, fn in (("KR", update_kr), ("HK", update_hk), ("TW", update_tw), ("JP", update_jp)):
        t0 = time.time()
        try:
            report[name] = fn()
        except Exception as e:  # noqa: BLE001
            log.error("flows %s failed: %s", name, e)
            report[name] = {"ok": False, "reason": repr(e)[:160]}
        report[name]["seconds"] = round(time.time() - t0, 1)
        log.info("flows %s: %s", name, report[name])
    return report
