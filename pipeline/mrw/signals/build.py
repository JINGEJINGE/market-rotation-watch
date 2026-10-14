"""Orchestrates all signal computations and writes data/outputs/latest.json."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from ..config import (ASIA_MARKETS, EVENTS_CFG, HARMONISED_SECTORS, MARKETS, PARAMS, THEMES, log)
from ..ingest.flows import load_flows
from ..universe.build import load_meta_cache
from . import metrics as M
from .core import Basket, Data, basket_returns, load_data

P = PARAMS


# ----------------------------------------------------------------------------- helpers
_LAST_CLOSED: dict[str, pd.Timestamp] = {}


def last_closed_session(m: str) -> pd.Timestamp:
    """Most recent session of market m whose close is already in the past (UTC)."""
    if m in _LAST_CLOSED:
        return _LAST_CLOSED[m]
    import exchange_calendars as xc
    cal = xc.get_calendar(MARKETS[m]["calendar"])
    now = pd.Timestamp.now(tz="UTC")
    s = cal.date_to_session(now.tz_convert(MARKETS[m]["tz"]).normalize().tz_localize(None), direction="previous")
    while cal.session_close(s) > now:
        s = cal.previous_session(s)
    _LAST_CLOSED[m] = s.tz_localize(None) if s.tzinfo else s
    return _LAST_CLOSED[m]


def market_dates(d: Data, m: str) -> pd.DatetimeIndex:
    """Trading dates for market m: days on which at least half the universe actually traded, up to the last closed session."""
    mm = "US" if m == "GLOBAL" else m
    tick = [t for t in d.universe.loc[d.universe.market == mm, "ticker"] if t in d.px_raw.columns]
    traded = d.px_raw[tick].notna().mean(axis=1) >= 0.5
    idx = d.px_raw.index[traded.values]
    return idx[idx <= last_closed_session(mm)]


def _idx(ret: pd.Series) -> pd.Series:
    return (1 + ret.fillna(0)).cumprod()


# ----------------------------------------------------------------------------- flows per ticker (value)
def flow_frames(d: Data) -> dict[str, pd.DataFrame]:
    """Per-market wide frames of daily net buying VALUE (local currency) by investor type."""
    out = {}
    kr = load_flows("KR")
    if not kr.empty:
        out["KR"] = {k: kr.pivot_table(index="date", columns="ticker", values=f"{k}_val", aggfunc="last")
                     for k in ("foreign", "inst", "retail")}
    tw = load_flows("TW")
    if not tw.empty:
        px = d.px.reindex(columns=[t for t in tw["ticker"].unique() if t in d.px.columns])
        frames = {}
        for k in ("foreign", "trust", "dealer"):
            q = tw.pivot_table(index="date", columns="ticker", values=f"{k}_qty", aggfunc="last")
            q = q.reindex(columns=px.columns)
            frames[k] = q * px.reindex(q.index)
        out["TW"] = frames
    hk = load_flows("HK")
    if not hk.empty:
        stocks = hk[hk.ticker != "TOTAL"]
        net = stocks.groupby(["date", "ticker"])["net"].sum().unstack()
        out["HK"] = {"southbound": net}
    return out


def basket_flow(flows: dict, b: Basket) -> dict[str, pd.Series]:
    """Sum of member flows by investor type (local currency), for a single-market basket."""
    m = b.market if b.type != "theme_country" else b.country
    if m not in flows:
        return {}
    res = {}
    for k, frame in flows[m].items():
        cols = [t for t in b.tickers if t in frame.columns]
        if not cols:
            continue
        res[k] = frame[cols].sum(axis=1, min_count=1)
        if m == "HK":
            res["coverage"] = frame[cols].notna().sum(axis=1)
    return res


SMART_FLOW = {"KR": ["foreign", "inst"], "TW": ["foreign", "trust"], "HK": ["southbound"]}


# ----------------------------------------------------------------------------- per-basket computation
def compute_basket(d: Data, b: Basket, flows: dict, market_turnover_local: dict, market_turnover_usd: dict) -> dict:
    m = b.market
    usd_only = (m == "GLOBAL")
    dates = market_dates(d, m)
    bench_local = (d.bench[m] if not usd_only else d.global_bench_usd).reindex(dates).ffill()
    bench_usd = (d.bench_usd[m] if not usd_only else d.global_bench_usd).reindex(dates).ffill()
    bm_ret = bench_local.pct_change(fill_method=None)
    bm_ret_usd = bench_usd.pct_change(fill_method=None)

    cw_l, ew_l, w = basket_returns(d, b, usd=usd_only)
    cw_u, ew_u, _ = basket_returns(d, b, usd=True)
    cw_l, ew_l, cw_u, ew_u = [s.reindex(dates) for s in (cw_l, ew_l, cw_u, ew_u)]

    res = M.residual(cw_l, bm_ret)
    res_u = M.residual(cw_u, bm_ret_usd)
    rr = M.rrg(_idx(cw_l), _idx(bm_ret))
    px_b = d.px[b.tickers].reindex(dates)
    br = M.breadth(px_b)

    # turnover share
    if usd_only:
        countries = {d.market_of[t] for t in b.tickers}
        tot = pd.concat([market_turnover_usd[c] for c in countries if c in market_turnover_usd], axis=1).sum(axis=1, min_count=1)
        bt = d.turnover_usd[b.tickers].sum(axis=1, min_count=1)
    else:
        tot = market_turnover_local[m]
        bt = (d.px[b.tickers] * d.vol[b.tickers]).sum(axis=1, min_count=1)
    share = (bt / tot).reindex(dates)
    base = P["turnover_baseline_days"]
    share_5 = share.rolling(5, min_periods=3).mean()
    s_mu, s_sd = share.rolling(base, min_periods=base // 2).mean(), share.rolling(base, min_periods=base // 2).std().replace(0, np.nan)
    share_z = (share_5 - s_mu) / s_sd
    share_1d_z = (share - s_mu) / s_sd

    rel = {n: (M.cum(cw_l, n) - M.cum(bm_ret, n)) for n in (1, 5, 20, 60)}
    rel_u = {n: (M.cum(cw_u, n) - M.cum(bm_ret_usd, n)) for n in (1, 5, 20, 60)}
    res_n = {n: res.rolling(n).sum() if n > 1 else res for n in (1, 5, 20)}
    res5_z = M.zscore(res_n[5])
    breadth_chg = br["pct_above_20"].diff(5)
    breadth_z = M.zscore(breadth_chg)

    # flows
    fl = basket_flow(flows, b)
    flow_series = None
    fm = b.market if b.type != "theme_country" else b.country
    if fl and fm in SMART_FLOW:
        parts = [fl[k] for k in SMART_FLOW[fm] if k in fl]
        if parts:
            flow_series = pd.concat(parts, axis=1).sum(axis=1, min_count=1).reindex(dates)
            if fm == "HK":  # top-10 coverage only: absence from the list is treated as zero net flow
                first = flow_series.first_valid_index()
                if first is not None:
                    flow_series.loc[first:] = flow_series.loc[first:].fillna(0.0)
    flow5 = flow_series.rolling(5, min_periods=3).sum() if flow_series is not None else None
    flow_z = M.zscore(flow5, min_periods=30) if flow5 is not None else None

    # composite (history)
    comps = {"residual_5d_z": res5_z, "turnover_share_z": share_z, "flow_z": flow_z, "breadth_change_z": breadth_z}
    wts = P["composite_weights"]
    num = sum(wts[k] * comps[k].astype(float).fillna(0.0) for k in comps if comps[k] is not None)
    den = sum(wts[k] * comps[k].notna().astype(float) for k in comps if comps[k] is not None)
    composite = (num / den.replace(0, np.nan)).clip(-4, 4)

    names = {t: str(n) for t, n in load_meta_cache()["name"].items() if isinstance(n, str)}
    names.update({t: str(n) for t, n in zip(d.universe["ticker"], d.universe["name"]) if isinstance(n, str)})
    last_date = dates[-1]
    ret_row = d.px[b.tickers].reindex(dates).pct_change(fill_method=None).iloc[-1]
    w_row = w.reindex(dates).iloc[-1] if len(w) else pd.Series(dtype=float)
    contrib = M.contributors(ret_row, w_row, names) if len(w_row) else None

    trail = rr[["rs_ratio", "rs_mom"]].tail(P["rrg_trail_days"]).round(2)
    rel_index = (_idx(cw_l) / _idx(bm_ret))
    rel_index = (rel_index / rel_index.iloc[-120:].iloc[0] * 100).tail(120) if len(rel_index) >= 120 else rel_index * 100

    latest = {
        "as_of": last_date.strftime("%Y-%m-%d"),
        "ret_1d": M.fl(M.last(cw_l)), "ret_5d": M.fl(M.last(M.cum(cw_l, 5))), "ret_20d": M.fl(M.last(M.cum(cw_l, 20))),
        "ret_1d_usd": M.fl(M.last(cw_u)), "ret_5d_usd": M.fl(M.last(M.cum(cw_u, 5))), "ret_20d_usd": M.fl(M.last(M.cum(cw_u, 20))),
        "ew_ret_1d": M.fl(M.last(ew_l)), "ew_ret_5d": M.fl(M.last(M.cum(ew_l, 5))),
        "ew_cw_gap_5d": M.fl(M.last(M.cum(ew_l, 5) - M.cum(cw_l, 5))),
        "rel_1d": M.fl(M.last(rel[1])), "rel_5d": M.fl(M.last(rel[5])), "rel_20d": M.fl(M.last(rel[20])), "rel_60d": M.fl(M.last(rel[60])),
        "rel_1d_usd": M.fl(M.last(rel_u[1])), "rel_5d_usd": M.fl(M.last(rel_u[5])), "rel_20d_usd": M.fl(M.last(rel_u[20])),
        "beta": M.fl(M.last(M.rolling_beta(cw_l, bm_ret)), 2),
        "residual_1d": M.fl(M.last(res_n[1])), "residual_5d": M.fl(M.last(res_n[5])), "residual_20d": M.fl(M.last(res_n[20])),
        "residual_5d_z": M.fl(M.last(res5_z), 2),
        "rs_ratio": M.fl(M.last(rr["rs_ratio"]), 2), "rs_mom": M.fl(M.last(rr["rs_mom"]), 2),
        "quadrant": M.last(rr["quadrant"]), "quadrant_prev": M.last(rr["quadrant"].shift(1)),
        "persist_days": int(M.last(rr["persist"], 0) or 0),
        "transition": bool(M.last(rr["quadrant"]) != M.last(rr["quadrant"].shift(1))) if M.last(rr["quadrant"]) else False,
        "turnover_share": M.fl(M.last(share), 5), "turnover_share_5d": M.fl(M.last(share_5), 5),
        "turnover_share_z": M.fl(M.last(share_z), 2), "turnover_share_1d_z": M.fl(M.last(share_1d_z), 2),
        "turnover_quadrant": M.turnover_quadrant(M.last(rel[5]), M.last(share_z)),
        "pct_above_20": M.fl(M.last(br["pct_above_20"]), 1), "pct_above_50": M.fl(M.last(br["pct_above_50"]), 1),
        "pct_above_200": M.fl(M.last(br["pct_above_200"]), 1),
        "breadth_change_5d": M.fl(M.last(breadth_chg), 1), "breadth_change_z": M.fl(M.last(breadth_z), 2),
        "advancers": int(M.last(br["advancers"], 0)), "decliners": int(M.last(br["decliners"], 0)),
        "flow_1d": M.fl(M.last(flow_series), 0) if flow_series is not None else None,
        "flow_5d": M.fl(M.last(flow5), 0) if flow5 is not None else None,
        "flow_20d": M.fl(M.last(flow_series.rolling(20, min_periods=10).sum()), 0) if flow_series is not None else None,
        "flow_z": M.fl(M.last(flow_z), 2) if flow_z is not None else None,
        "flow_as_of": flow_series.dropna().index[-1].strftime("%Y-%m-%d") if flow_series is not None and flow_series.notna().any() else None,
        "flow_coverage": int(M.last(fl["coverage"], 0)) if "coverage" in fl else None,
        "flow_detail": {k: M.fl(M.last(v.reindex(dates).rolling(5, min_periods=3).sum()), 0) for k, v in fl.items() if k != "coverage"} if fl else None,
        "composite": M.fl(M.last(composite), 2),
        "composite_components": {k: M.fl(M.last(v), 2) for k, v in comps.items() if v is not None},
    }
    series = {
        "rrg_trail": [[M.fl(a, 2), M.fl(bm, 2)] for a, bm in trail.values.tolist()],
        "rel_index_120d": [M.fl(v, 2) for v in rel_index.tolist()],
        "turnover_share_60d": [M.fl(v, 5) for v in share.tail(60).tolist()],
        "flow_20d_series": [M.fl(v, 0) for v in flow_series.tail(20).tolist()] if flow_series is not None else None,
    }
    history = pd.DataFrame({"quadrant": rr["quadrant"], "composite": composite, "residual": res,
                            "share_z": share_z, "rel5": rel[5]})
    return {"basket": b, "latest": latest, "series": series, "contributors": contrib, "history": history,
            "n": len(b.tickers)}


# ----------------------------------------------------------------------------- regime
def compute_regime(d: Data, results: list[dict]) -> dict:
    out = {}
    for m in MARKETS:
        dates = market_dates(d, m)
        bm = d.bench[m].reindex(dates).ffill().pct_change(fill_method=None)
        sec = [r for r in results if r["basket"].type == "sector" and r["basket"].market == m]
        if not sec:
            continue
        rets = pd.DataFrame({r["basket"].sector: r["history"]["rel5"] for r in sec})  # placeholder to align
        # recompute 1d sector returns for dispersion/correlation
        rets = pd.DataFrame({r["basket"].sector: basket_returns(d, r["basket"], usd=False)[0].reindex(dates) for r in sec})
        disp = rets.std(axis=1)
        corr_w = P["corr_window"]
        avg_corr = pd.Series(index=dates, dtype=float)
        vals = rets.values
        for i in range(corr_w, len(dates)):
            c = np.corrcoef(np.nan_to_num(vals[i - corr_w + 1:i + 1].T))
            n = c.shape[0]
            avg_corr.iloc[i] = (c.sum() - n) / (n * (n - 1)) if n > 1 else np.nan
        disp_z = M.zscore(disp)
        corr_pct = avg_corr.rolling(P["zscore_lookback_days"], min_periods=60).rank(pct=True)
        vol20 = bm.rolling(20).std() * np.sqrt(252)
        bm_z = (bm / bm.rolling(60).std())
        dz, cp, bz = M.last(disp_z), M.last(corr_pct), M.last(bm_z)
        if dz is not None and cp is not None:
            if dz > 0.5 and cp < 0.5:
                label = "Rotation day"
            elif bz is not None and abs(bz) > 1.0 and cp > 0.5:
                label = "Beta day"
            elif dz < -0.5 and cp > 0.6:
                label = "Low-dispersion drift"
            else:
                label = "Mixed"
        else:
            label = "n/a"
        mkt_basket = next((r for r in results if r["basket"].id == f"{m}:MARKET"), None)
        out[m] = {
            "as_of": dates[-1].strftime("%Y-%m-%d"),
            "benchmark": MARKETS[m]["benchmark_name"], "bench_level": M.fl(M.last(d.bench[m].reindex(dates).ffill()), 2),
            "bench_ret_1d": M.fl(M.last(bm)), "bench_ret_5d": M.fl(M.last(M.cum(bm, 5))), "bench_ret_20d": M.fl(M.last(M.cum(bm, 20))),
            "bench_ret_1d_usd": M.fl(M.last(d.bench_usd[m].reindex(dates).ffill().pct_change(fill_method=None))),
            "bench_ret_5d_usd": M.fl(M.last(M.cum(d.bench_usd[m].reindex(dates).ffill().pct_change(fill_method=None), 5))),
            "fx_ret_5d": M.fl(M.last(M.cum((1 / d.fx[m]).reindex(dates).ffill().pct_change(fill_method=None), 5))),
            "bench_ret_z": M.fl(bz, 2), "realised_vol_20d": M.fl(M.last(vol20), 3),
            "dispersion": M.fl(M.last(disp), 4), "dispersion_z": M.fl(dz, 2),
            "avg_corr": M.fl(M.last(avg_corr), 2), "avg_corr_pctile": M.fl(cp, 2),
            "label": label,
            "breadth_pct_above_20": mkt_basket["latest"]["pct_above_20"] if mkt_basket else None,
            "breadth_pct_above_50": mkt_basket["latest"]["pct_above_50"] if mkt_basket else None,
            "advancers": mkt_basket["latest"]["advancers"] if mkt_basket else None,
            "decliners": mkt_basket["latest"]["decliners"] if mkt_basket else None,
            "ew_cw_gap_5d": mkt_basket["latest"]["ew_cw_gap_5d"] if mkt_basket else None,
            "dispersion_series_60d": [M.fl(v, 4) for v in disp.tail(60).tolist()],
            "avg_corr_series_60d": [M.fl(v, 2) for v in avg_corr.tail(60).tolist()],
        }
    return out


# ----------------------------------------------------------------------------- market-level flows
def market_flows(d: Data) -> dict:
    out = {}
    kr = load_flows("KR")
    if not kr.empty:
        g = kr.groupby("date")[["foreign_val", "inst_val", "retail_val"]].sum()
        out["KR"] = _flow_summary(g.rename(columns=lambda c: c.replace("_val", "")), "KRW")
    tw = load_flows("TW")
    if not tw.empty:
        px = d.px
        tw = tw.copy()
        tw["close"] = [px.at[dte, t] if (t in px.columns and dte in px.index) else np.nan for dte, t in zip(tw["date"], tw["ticker"])]
        for k in ("foreign", "trust", "dealer"):
            tw[k] = tw[f"{k}_qty"] * tw["close"]
        g = tw.groupby("date")[["foreign", "trust", "dealer"]].sum()
        out["TW"] = _flow_summary(g, "TWD", note="Universe stocks only (top-150 + theme members)")
    hk = load_flows("HK")
    if not hk.empty:
        tot = hk[hk.ticker == "TOTAL"].groupby("date")[["buy", "sell", "net"]].sum()
        s = _flow_summary(tot[["net"]].rename(columns={"net": "southbound_net"}), "HKD",
                          note="Buy minus sell turnover, SSE + SZSE channels")
        top = hk[(hk.ticker != "TOTAL") & (hk.date == hk.date.max())].groupby(["ticker", "name"])["net"].sum().sort_values()
        s["top_stocks_latest"] = {"date": hk.date.max().strftime("%Y-%m-%d"),
                                  "buyers": [{"ticker": t, "name": n, "net": M.fl(v, 0)} for (t, n), v in top.tail(5)[::-1].items()],
                                  "sellers": [{"ticker": t, "name": n, "net": M.fl(v, 0)} for (t, n), v in top.head(5).items()]}
        out["HK"] = s
    jp = load_flows("JP")
    if not jp.empty:
        jp = jp.sort_values("week_end")
        cols = [c for c in ("foreigners", "individuals", "investment_trusts", "securities_cos", "business_cos", "insurers", "banks", "trust_banks", "proprietary") if c in jp.columns]
        out["JP"] = {"currency": "JPY", "frequency": "weekly", "as_of": str(jp["week_end"].iloc[-1]),
                     "note": "JPX weekly investor-type trading, TSE Prime, value; one-week publication lag",
                     "latest": {c: M.fl(jp[c].iloc[-1], 0) for c in cols},
                     "series": [{"week_end": str(w), **{c: M.fl(v, 0) for c, v in zip(cols, row)}}
                                for w, row in zip(jp["week_end"].tail(12), jp[cols].tail(12).values)]}
    return out


def _flow_summary(g: pd.DataFrame, ccy: str, note: str | None = None) -> dict:
    g = g.sort_index()
    out = {"currency": ccy, "frequency": "daily", "as_of": g.index[-1].strftime("%Y-%m-%d"), "note": note, "investors": {}}
    for c in g.columns:
        s = g[c]
        s5 = s.rolling(5, min_periods=3).sum()
        out["investors"][c] = {"d1": M.fl(s.iloc[-1], 0), "d5": M.fl(s5.iloc[-1], 0),
                               "d20": M.fl(s.rolling(20, min_periods=10).sum().iloc[-1], 0),
                               "z5": M.fl(M.last(M.zscore(s5, min_periods=40)), 2),
                               "series_20d": [{"date": i.strftime("%Y-%m-%d"), "v": M.fl(v, 0)} for i, v in s.tail(20).items()]}
    return out


# ----------------------------------------------------------------------------- lead-lag
def compute_leadlag(d: Data, results: list[dict], run: str) -> dict:
    by_id = {r["basket"].id: r for r in results}
    out = {}
    us_dates = market_dates(d, "US")
    for key in THEMES:
        us = by_id.get(f"THEME:{key}:US")
        if us is None:
            continue
        us_ret = basket_returns(d, us["basket"], usd=True)[0].reindex(us_dates).dropna()
        entry = {}
        for c in ASIA_MARKETS:
            r = by_id.get(f"THEME:{key}:{c}")
            if r is None:
                continue
            a_dates = market_dates(d, c)
            a_ret = basket_returns(d, r["basket"], usd=True)[0].reindex(a_dates).dropna()
            # pair each Asia date with the last US date strictly before it
            pos = us_ret.index.searchsorted(a_ret.index, side="left") - 1
            ok = pos >= 0
            pairs = pd.DataFrame({"asia": a_ret.values[ok], "us": us_ret.values[pos[ok]]}, index=a_ret.index[ok])
            pairs = pairs.tail(P["leadlag_window"] * 4)
            w = P["leadlag_window"]
            cov = pairs["asia"].rolling(w).cov(pairs["us"])
            var = pairs["us"].rolling(w).var()
            slope = (cov / var.replace(0, np.nan))
            corr = pairs["asia"].rolling(w).corr(pairs["us"])
            s, cr = M.last(slope), M.last(corr)
            last_us_date = us_ret.index[-1]
            last_us_ret = float(us_ret.iloc[-1])
            if run == "us" or last_us_date > pairs.index[-1]:
                implied = s * last_us_ret if s is not None else None
                entry[c] = {"mode": "implied", "us_date": last_us_date.strftime("%Y-%m-%d"), "us_ret": M.fl(last_us_ret),
                            "slope": M.fl(s, 2), "corr": M.fl(cr, 2), "implied_asia_ret": M.fl(implied), "realised_asia_ret": None}
            else:
                last_pair = pairs.iloc[-1]
                implied = s * last_pair["us"] if s is not None else None
                entry[c] = {"mode": "realised", "asia_date": pairs.index[-1].strftime("%Y-%m-%d"),
                            "us_ret": M.fl(last_pair["us"]), "slope": M.fl(s, 2), "corr": M.fl(cr, 2),
                            "implied_asia_ret": M.fl(implied), "realised_asia_ret": M.fl(last_pair["asia"]),
                            "surprise": M.fl(last_pair["asia"] - implied) if implied is not None else None}
        if entry:
            out[key] = entry
    return out


# ----------------------------------------------------------------------------- scorecard
def compute_scorecard(results: list[dict]) -> dict:
    rows = []
    thr = P["composite_threshold"]
    for r in results:
        b = r["basket"]
        if b.type not in ("sector", "theme"):
            continue
        h = r["history"].dropna(subset=["residual"])
        if len(h) < 120:
            continue
        fwd5 = h["residual"].rolling(5).sum().shift(-5)
        fwd20 = h["residual"].rolling(20).sum().shift(-20)
        q = h["quadrant"]
        ev_lead = (q == "Leading") & (q.shift(1) != "Leading") & q.shift(1).notna()
        ev_improve = (q == "Improving") & (q.shift(1) == "Lagging")
        c = h["composite"]
        ev_comp = (c >= thr) & (c.shift(1) < thr)
        ev_comp_neg = (c <= -thr) & (c.shift(1) > -thr)
        for name, ev, sign in (("rrg_leading_entry", ev_lead, 1), ("rrg_improving_entry", ev_improve, 1),
                               ("composite_above", ev_comp, 1), ("composite_below", ev_comp_neg, -1)):
            for dte in h.index[ev.values]:
                f5, f20 = fwd5.get(dte), fwd20.get(dte)
                if f5 is None or np.isnan(f5):
                    continue
                rows.append({"signal": name, "market": b.market, "type": b.type, "basket": b.id, "date": dte,
                             "fwd5": sign * f5, "fwd20": sign * f20 if f20 is not None and not np.isnan(f20) else np.nan})
    if not rows:
        return {"note": "insufficient history", "by_signal": []}
    ev = pd.DataFrame(rows)
    ev = ev[ev["date"] >= ev["date"].max() - pd.Timedelta(days=730)]

    def agg(g):
        return pd.Series({"n": len(g), "hit_5d": (g["fwd5"] > 0).mean(), "avg_5d": g["fwd5"].mean(),
                          "hit_20d": (g["fwd20"] > 0).mean(), "avg_20d": g["fwd20"].mean()})

    by_sig = ev.groupby(["signal"]).apply(agg, include_groups=False).reset_index()
    by_sig_mkt = ev.groupby(["signal", "market"]).apply(agg, include_groups=False).reset_index()
    recent = ev.sort_values("date").tail(30)
    rec = lambda df: [{k: (M.fl(v, 4) if isinstance(v, (float, np.floating)) else (v.strftime("%Y-%m-%d") if isinstance(v, pd.Timestamp) else v))  # noqa: E731
                       for k, v in row.items()} for row in df.to_dict("records")]
    return {"window": "last 2 years, forward beta-adjusted relative return; sign flipped for negative signals",
            "by_signal": rec(by_sig), "by_signal_market": rec(by_sig_mkt), "recent_events": rec(recent)}


# ----------------------------------------------------------------------------- events
def upcoming_events(as_of: pd.Timestamp, days: int = 4) -> list[dict]:
    import exchange_calendars as xc
    out = []
    end = as_of + pd.Timedelta(days=days)
    for e in EVENTS_CFG.get("events", []):
        dte = pd.Timestamp(e["date"])
        if as_of <= dte <= end:
            out.append({"date": dte.strftime("%Y-%m-%d"), "market": e["market"], "label": e["label"], "kind": "event"})
    for s in EVENTS_CFG.get("seasons", []):
        if pd.Timestamp(s["start"]) <= as_of <= pd.Timestamp(s["end"]):
            out.append({"date": None, "market": "ALL", "label": s["label"], "kind": "season"})
    for m, c in MARKETS.items():
        cal = xc.get_calendar(c["calendar"])
        for dte in pd.date_range(as_of, end):
            if dte.weekday() < 5 and not cal.is_session(dte):
                out.append({"date": dte.strftime("%Y-%m-%d"), "market": m, "label": f"{MARKETS[m]['name']} market holiday", "kind": "holiday"})
    return sorted(out, key=lambda x: (x["date"] or "", x["market"]))


# ----------------------------------------------------------------------------- assemble
def build_outputs(run: str, source_report: dict | None = None) -> dict:
    d = load_data()
    flows = flow_frames(d)
    mt_local, mt_usd = {}, {}
    for m in MARKETS:
        tick = [t for t in d.universe.loc[d.universe.market == m, "ticker"] if t in d.px.columns]
        mt_local[m] = (d.px[tick] * d.vol[tick]).sum(axis=1, min_count=1)
        mt_usd[m] = d.turnover_usd[tick].sum(axis=1, min_count=1)

    results = []
    for b in d.baskets:
        try:
            results.append(compute_basket(d, b, flows, mt_local, mt_usd))
        except Exception as e:  # noqa: BLE001
            log.warning("basket %s failed: %s", b.id, repr(e)[:160])
    log.info("computed %d baskets", len(results))

    regime = compute_regime(d, results)
    mflows = market_flows(d)
    leadlag = compute_leadlag(d, results, run)
    scorecard = compute_scorecard(results)

    baskets_out = []
    for r in results:
        b = r["basket"]
        baskets_out.append({"id": b.id, "type": b.type, "market": b.market, "name": b.name, "theme": b.theme,
                            "sector": b.sector, "country": b.country, "n": r["n"], "tickers": b.tickers,
                            **r["latest"], "series": r["series"], "contributors": r["contributors"]})

    # cross-market heatmap: harmonised sector x market
    heat = {}
    for metric in ("rel_5d_usd", "residual_5d_z", "turnover_share_z", "rel_20d_usd", "composite", "flow_z"):
        heat[metric] = [[next((x[metric] for x in baskets_out if x["type"] == "sector" and x["market"] == m and x["sector"] == s), None)
                         for m in MARKETS] for s in HARMONISED_SECTORS]
    heatmap = {"sectors": HARMONISED_SECTORS, "markets": list(MARKETS), "values": heat}

    themes_out = []
    for key, th in THEMES.items():
        total = next((x for x in baskets_out if x["id"] == f"THEME:{key}"), None)
        if total is None:
            continue
        countries = {c: next((x for x in baskets_out if x["id"] == f"THEME:{key}:{c}"), None) for c in th["members"]}
        themes_out.append({"id": key, "name": th["name"], "description": th.get("description"), "total": total,
                           "countries": {c: v for c, v in countries.items() if v}, "leadlag": leadlag.get(key)})

    as_of = {m: regime[m]["as_of"] for m in regime}
    latest_asof = max(pd.Timestamp(v) for v in as_of.values())
    ranked = sorted([x for x in baskets_out if x["type"] in ("sector", "theme") and x["composite"] is not None],
                    key=lambda x: x["composite"], reverse=True)
    out = {
        "meta": {"run": run, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 "as_of": as_of, "sources": source_report or {}, "params": P,
                 "basket_count": len(baskets_out), "universe_counts": d.universe.groupby("market").size().to_dict()},
        "regime": regime,
        "baskets": baskets_out,
        "leaders": [x["id"] for x in ranked[:8]],
        "laggards": [x["id"] for x in ranked[-8:]][::-1],
        "transitions": [{"id": x["id"], "name": x["name"], "market": x["market"], "from": x["quadrant_prev"], "to": x["quadrant"]}
                        for x in baskets_out if x["type"] in ("sector", "theme") and x["transition"] and x["quadrant_prev"]],
        "persistence_milestones": [{"id": x["id"], "name": x["name"], "market": x["market"], "quadrant": x["quadrant"], "days": x["persist_days"]}
                                   for x in baskets_out if x["type"] in ("sector", "theme") and x["persist_days"] in (5, 10, 20, 40)],
        "heatmap": heatmap,
        "themes": themes_out,
        "market_flows": mflows,
        "events": upcoming_events(latest_asof),
        "scorecard": scorecard,
    }
    return out
