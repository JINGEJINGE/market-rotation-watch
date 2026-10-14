"""Data preparation: wide price/volume frames, FX conversion, basket definitions and basket return series."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import HARMONISED_SECTORS, MARKETS, PARAMS, THEMES, log
from ..ingest.prices import load_prices, wide
from ..universe.build import load_all_universes, load_meta_cache

MIN_BASKET = 3


@dataclass
class Basket:
    id: str
    type: str            # sector | theme | theme_country | market
    market: str          # market code, or GLOBAL for cross-market themes
    name: str
    tickers: list[str]
    theme: str | None = None
    sector: str | None = None
    country: str | None = None


@dataclass
class Data:
    px: pd.DataFrame            # local close, date x ticker (forward-filled up to 5 days)
    px_raw: pd.DataFrame        # as downloaded, NaN on non-trading days
    vol: pd.DataFrame
    px_usd: pd.DataFrame
    turnover_usd: pd.DataFrame  # px_usd * vol
    fx: dict[str, pd.Series]    # market -> local per USD (1.0 for US)
    shares: pd.Series           # ticker -> shares outstanding (approx)
    market_of: pd.Series        # ticker -> market code
    universe: pd.DataFrame
    bench: dict[str, pd.Series]      # market -> benchmark close (local)
    bench_usd: dict[str, pd.Series]
    global_bench_usd: pd.Series
    baskets: list[Basket] = field(default_factory=list)


def _market_from_suffix(t: str) -> str:
    if t.endswith((".KS", ".KQ")):
        return "KR"
    if t.endswith(".HK"):
        return "HK"
    if t.endswith(".T"):
        return "JP"
    if t.endswith((".TW", ".TWO")):
        return "TW"
    return "US"


def load_data() -> Data:
    uni = load_all_universes()
    meta = load_meta_cache()
    long = load_prices()
    px = wide(long, "close")
    vol = wide(long, "volume").reindex(columns=px.columns)
    px_raw = px.copy()
    px = px.ffill(limit=5)

    # FX: Yahoo quotes are local per USD (KRW=X = KRW per USD)
    fx: dict[str, pd.Series] = {}
    for m, c in MARKETS.items():
        if c.get("fx") and c["fx"] in px.columns:
            fx[m] = px[c["fx"]].ffill()
        else:
            fx[m] = pd.Series(1.0, index=px.index)

    market_of = pd.Series({t: _market_from_suffix(t) for t in px.columns})
    for _, r in uni.iterrows():
        market_of[r["ticker"]] = r["market"]
    rate = pd.DataFrame({t: fx[market_of[t]] for t in px.columns}, index=px.index)
    # FX tickers and indices themselves are not converted
    for t in px.columns:
        if t.endswith("=X") or t.startswith("^"):
            rate[t] = 1.0
    px_usd = px / rate
    turnover_usd = px_usd * vol

    # shares outstanding: metadata, else mcap / last close, else NaN (equal-weight fallback)
    shares = pd.Series(np.nan, index=px.columns)
    last_px = px.ffill().iloc[-1]
    for t in px.columns:
        s = meta["shares"].get(t) if t in meta.index else np.nan
        if pd.isna(s) or s <= 0:
            mc = meta["mcap"].get(t) if t in meta.index else np.nan
            if not pd.isna(mc) and last_px.get(t, np.nan) > 0:
                s = mc / last_px[t]
        shares[t] = s
    for _, r in uni.iterrows():
        if pd.isna(shares.get(r["ticker"])) and not pd.isna(r.get("mcap_local")) and last_px.get(r["ticker"], 0) > 0:
            shares[r["ticker"]] = r["mcap_local"] / last_px[r["ticker"]]

    bench = {m: px[c["benchmark"]].ffill() for m, c in MARKETS.items() if c["benchmark"] in px.columns}
    bench_usd = {m: (bench[m] / fx[m]) for m in bench}
    global_bench_usd = px["ACWI"].ffill() if "ACWI" in px.columns else pd.concat(bench_usd.values(), axis=1).pct_change().mean(axis=1).add(1).cumprod()

    d = Data(px=px, px_raw=px_raw, vol=vol, px_usd=px_usd, turnover_usd=turnover_usd, fx=fx, shares=shares, market_of=market_of,
             universe=uni, bench=bench, bench_usd=bench_usd, global_bench_usd=global_bench_usd)
    d.baskets = define_baskets(d)
    return d


def define_baskets(d: Data) -> list[Basket]:
    out: list[Basket] = []
    have = set(d.px.columns)
    for m in MARKETS:
        u = d.universe[d.universe.market == m]
        tick = [t for t in u["ticker"] if t in have]
        out.append(Basket(id=f"{m}:MARKET", type="market", market=m, name=f"{MARKETS[m]['name']} universe", tickers=tick))
        for sec in HARMONISED_SECTORS:
            tick = [t for t in u.loc[u.sector == sec, "ticker"] if t in have]
            if len(tick) >= MIN_BASKET:
                out.append(Basket(id=f"{m}:{sec}", type="sector", market=m, name=sec, tickers=tick, sector=sec))
    for key, th in THEMES.items():
        all_t = []
        for country, members in th["members"].items():
            tick = [t for t in members if t in have]
            all_t += tick
            if len(tick) >= 2:
                out.append(Basket(id=f"THEME:{key}:{country}", type="theme_country", market=country,
                                  name=f"{th['name']} — {MARKETS[country]['name']}", tickers=tick, theme=key, country=country))
        all_t = list(dict.fromkeys(all_t))
        if len(all_t) >= MIN_BASKET:
            out.append(Basket(id=f"THEME:{key}", type="theme", market="GLOBAL", name=th["name"], tickers=all_t, theme=key))
    log.info("defined %d baskets", len(out))
    return out


def basket_returns(d: Data, b: Basket, usd: bool) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """Return (cap-weighted daily return, equal-weighted daily return, weights frame used for cap-weighting)."""
    px = (d.px_usd if usd else d.px)[b.tickers]
    ret = px.pct_change(fill_method=None)
    ret = ret.where(ret.abs() < 0.6)  # drop corporate-action glitches
    sh = d.shares.reindex(b.tickers)
    if sh.notna().sum() >= max(2, int(0.5 * len(b.tickers))):
        mcap = px.shift(1).mul(sh.fillna(sh.median()), axis=1)
        mcap = mcap.where(ret.notna())
        w = cap_weights(mcap.div(mcap.sum(axis=1), axis=0), PARAMS.get("max_weight", 1.0))
        cw = (w * ret).sum(axis=1, min_count=1)
    else:
        w = ret.notna().astype(float)
        w = w.div(w.sum(axis=1), axis=0)
        cw = ret.mean(axis=1)
    ew = ret.mean(axis=1)
    return cw, ew, w


def cap_weights(w: pd.DataFrame, cap: float, iters: int = 6) -> pd.DataFrame:
    """Cap each name at `cap` of the basket and redistribute the excess pro rata to the uncapped names."""
    if cap >= 1.0:
        return w
    w = w.copy()
    for _ in range(iters):
        over = w > cap
        if not over.any().any():
            break
        excess = (w.where(over) - cap).sum(axis=1).fillna(0.0)
        w = w.where(~over, cap)
        rest = w.where(~over)
        rest_sum = rest.sum(axis=1)
        add = rest.div(rest_sum.replace(0, np.nan), axis=0).mul(excess, axis=0).fillna(0.0)
        w = w + add
    return w
