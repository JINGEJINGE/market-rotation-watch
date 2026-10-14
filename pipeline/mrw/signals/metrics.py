"""Per-basket signal computations. Every function returns pandas Series/DataFrames over the full
history so that both the latest snapshot and the scorecard backfill come from the same code."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import PARAMS

P = PARAMS


def cum(ret: pd.Series, n: int) -> pd.Series:
    return (1 + ret).rolling(n).apply(np.prod, raw=True) - 1 if n > 1 else ret


def zscore(s: pd.Series, lookback: int | None = None, min_periods: int = 60) -> pd.Series:
    lb = lookback or P["zscore_lookback_days"]
    mu = s.rolling(lb, min_periods=min_periods).mean()
    sd = s.rolling(lb, min_periods=min_periods).std()
    return (s - mu) / sd.replace(0, np.nan)


def rolling_beta(r: pd.Series, m: pd.Series, window: int | None = None) -> pd.Series:
    w = window or P["beta_window"]
    cov = r.rolling(w, min_periods=w // 2).cov(m)
    var = m.rolling(w, min_periods=w // 2).var()
    return (cov / var.replace(0, np.nan)).clip(-3, 5)


def residual(r: pd.Series, m: pd.Series) -> pd.Series:
    """Beta-adjusted residual daily return (basket minus beta x benchmark)."""
    beta = rolling_beta(r, m).shift(1).fillna(1.0)  # use yesterday's beta: no look-ahead
    return r - beta * m


def rrg(basket_idx: pd.Series, bench_idx: pd.Series) -> pd.DataFrame:
    """JdK-style RS-Ratio / RS-Momentum approximation on daily data.

    RS-Ratio  = 100 + z-score of the (5-day smoothed) relative-strength line over the ratio window (1 unit = 1 sigma).
    RS-Momentum = 100 + the 5-day change of RS-Ratio, scaled by its own rolling std, smoothed over 3 days.
    """
    rs = (basket_idx / bench_idx).replace([np.inf, -np.inf], np.nan)
    rs = rs.ewm(span=5, min_periods=3).mean()
    n1, n2 = P["rrg_ratio_window"], P["rrg_mom_window"]
    ratio = 100 + (rs - rs.rolling(n1, min_periods=n1 // 2).mean()) / rs.rolling(n1, min_periods=n1 // 2).std().replace(0, np.nan)
    chg = ratio.diff(5)
    mom = 100 + (chg / chg.rolling(n1, min_periods=n2).std().replace(0, np.nan)).rolling(3, min_periods=1).mean()
    q = pd.Series(np.where(ratio >= 100, np.where(mom >= 100, "Leading", "Weakening"),
                           np.where(mom >= 100, "Improving", "Lagging")), index=rs.index)
    q = q.where(ratio.notna() & mom.notna())
    change = (q != q.shift(1)).cumsum()
    persist = q.groupby(change).cumcount() + 1
    persist = persist.where(q.notna())
    return pd.DataFrame({"rs_ratio": ratio, "rs_mom": mom, "quadrant": q, "persist": persist})


def breadth(px: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for n in (20, 50, 200):
        ma = px.rolling(n, min_periods=n // 2).mean()
        above = (px > ma).where(px.notna() & ma.notna())
        out[f"pct_above_{n}"] = above.mean(axis=1) * 100
    ret = px.pct_change(fill_method=None)
    adv = (ret > 0).sum(axis=1)
    dec = (ret < 0).sum(axis=1)
    out["advancers"] = adv
    out["decliners"] = dec
    out["ad_ratio"] = (adv - dec) / (adv + dec).replace(0, np.nan)
    return pd.DataFrame(out)


def contributors(ret_row: pd.Series, w_row: pd.Series, names: dict[str, str], k: int = 3) -> dict:
    """Top contributors to a one-day cap-weighted basket return."""
    c = (ret_row * w_row).dropna()
    total = c.sum()
    c = c.sort_values()
    top = c.tail(k)[::-1]
    bottom = c.head(k)
    ab = c.abs()
    hhi = float(((ab / ab.sum()) ** 2).sum()) if ab.sum() > 0 else np.nan
    share = lambda v: (float(v) / total) if abs(total) > 0.002 else np.nan  # noqa: E731
    fmt = lambda s: [{"ticker": t, "name": names.get(t, t), "ret": float(ret_row[t]), "contrib": float(v),  # noqa: E731
                      "share_of_move": share(v)} for t, v in s.items()]
    return {"total": float(total), "top": fmt(top), "bottom": fmt(bottom), "hhi": hhi, "n": int(len(c))}


MIN_NAMES = 5          # baskets with fewer names are flagged "thin"
MAX_SHARE = 0.60       # one contributor above this share of the day's move flags the basket "concentrated"


def basket_flags(n: int, contrib: dict | None) -> dict:
    """Minimum-size and concentration flags for the leaders/laggards lists (flag, never drop)."""
    thin = n < MIN_NAMES
    worst = None
    if contrib:
        for c in contrib.get("top", []) + contrib.get("bottom", []):
            sh = c.get("share_of_move")
            if sh is not None and not np.isnan(sh) and abs(sh) > MAX_SHARE and (worst is None or abs(sh) > abs(worst["share_of_move"])):
                worst = c
    concentrated = worst is not None
    reasons = []
    if thin:
        reasons.append(f"n<{MIN_NAMES}")
    if concentrated:
        reasons.append(f"one name {abs(worst['share_of_move']) * 100:.0f}% of move")
    return {"thin": thin, "concentrated": concentrated, "flag_reason": "; ".join(reasons) or None,
            "flag_name": worst["name"] if concentrated else None,
            "flag_share": round(abs(worst["share_of_move"]), 3) if concentrated else None}


def turnover_quadrant(rel_5d: float, share_z: float) -> str | None:
    if rel_5d is None or share_z is None or np.isnan(rel_5d) or np.isnan(share_z):
        return None
    if rel_5d >= 0:
        return "Accumulation" if share_z >= 0 else "Thin drift"
    return "Distribution" if share_z >= 0 else "Apathy"


def last(s: pd.Series, default=None):
    if s is None or len(s) == 0:
        return default
    v = s.iloc[-1]
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return default
    return v


def fl(v, nd: int = 4):
    """float or None, rounded."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, nd)
