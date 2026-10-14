"""Deterministic digest tables (Markdown) from the computed outputs."""
from __future__ import annotations

from ..config import MARKETS, ASIA_MARKETS


def pct(v, nd: int = 1) -> str:
    return "–" if v is None else f"{v * 100:+.{nd}f}%"


def num(v, nd: int = 2) -> str:
    return "–" if v is None else f"{v:+.{nd}f}"


def money(v, ccy: str) -> str:
    if v is None:
        return "–"
    units = {"KRW": (1e9, "bn"), "TWD": (1e9, "bn"), "HKD": (1e6, "m"), "JPY": (1e9, "bn"), "USD": (1e6, "m")}
    div, suf = units.get(ccy, (1e6, "m"))
    return f"{v / div:+,.1f}{suf} {ccy}"


def _bk(out: dict, bid: str) -> dict | None:
    return next((b for b in out["baskets"] if b["id"] == bid), None)


def _label(b: dict) -> str:
    if b["type"] == "theme":
        return f"{b['name']} (theme)"
    return f"{MARKETS[b['market']]['name']} · {b['name']}"


def regime_lines(out: dict, run: str) -> list[str]:
    order = ["US"] + ASIA_MARKETS if run == "us" else ASIA_MARKETS + ["US"]
    lines = []
    for m in order:
        r = out["regime"].get(m)
        if not r:
            continue
        fx = f", FX {pct(r['fx_ret_5d'])} 5d" if m != "US" and r.get("fx_ret_5d") is not None else ""
        lines.append(f"- **{MARKETS[m]['name']}** ({r['as_of']}): {r['benchmark']} {pct(r['bench_ret_1d'])} "
                     f"(5d {pct(r['bench_ret_5d'])}{fx}) · dispersion z {num(r['dispersion_z'])} · "
                     f"sector corr pctile {r['avg_corr_pctile'] if r['avg_corr_pctile'] is not None else '–'} · "
                     f"breadth {r['breadth_pct_above_20'] if r['breadth_pct_above_20'] is not None else '–'}% >20DMA · "
                     f"EW–CW 5d {pct(r['ew_cw_gap_5d'])} → **{r['label']}**")
    return lines


SIGNAL_NAMES = {"rrg_leading_entry": "entered Leading", "rrg_improving_entry": "Lagging→Improving",
                "composite_above": "composite ≥ +threshold", "composite_below": "composite ≤ −threshold"}


def _score(out: dict, signal: str, market: str) -> dict | None:
    sc = out.get("scorecard", {})
    return next((r for r in sc.get("by_signal_market", []) if r["signal"] == signal and r["market"] == market), None) \
        or next((r for r in sc.get("by_signal", []) if r["signal"] == signal), None)


def record(r: dict | None) -> str:
    """'54% n=396' plus the 'unconfirmed signal' label below a 50% five-day hit rate."""
    if not r or r.get("hit_5d") is None:
        return "–"
    txt = f"{r['hit_5d'] * 100:.0f}% n={int(r['n'])}"
    return txt + (" · unconfirmed signal" if r["hit_5d"] < 0.5 else "")


def basket_signal(out: dict, b: dict) -> str:
    """The scorecard signal type this basket is showing today, with its 5-day hit rate and n in its market."""
    thr = out["meta"]["params"].get("composite_threshold", 1.5)
    c = b.get("composite")
    if b.get("transition") and b.get("quadrant") == "Leading":
        sig = "rrg_leading_entry"
    elif b.get("transition") and b.get("quadrant") == "Improving" and b.get("quadrant_prev") == "Lagging":
        sig = "rrg_improving_entry"
    elif c is not None and c >= thr:
        sig = "composite_above"
    elif c is not None and c <= -thr:
        sig = "composite_below"
    else:
        return "–"
    return f"{SIGNAL_NAMES[sig]}: {record(_score(out, sig, b['market']))}"


def excluded_line(flagged: list[dict]) -> list[str]:
    if not flagged:
        return []
    parts = []
    for f in flagged:
        label = f"{MARKETS[f['market']]['name']} {f['name']}" if f["market"] in MARKETS else f"{f['name']} (theme)"
        why = []
        if f.get("concentrated"):
            why.append(f"{f['flag_name']} {f['flag_share'] * 100:.0f}% of move")
        if f.get("thin"):
            why.append(f"only {f['n']} names")
        parts.append(f"{label} ({', '.join(why)}; score {num(f['composite'])})")
    return ["", "_Excluded as concentrated or too small: " + "; ".join(parts) + "._"]


def movers_table(out: dict, ids: list[str], title: str) -> list[str]:
    lines = [f"**{title}**", "", "| Basket | Score | Resid 5d (z) | Turnover z | Flow z | Breadth Δ5d | RRG | Days | Top contributor | Signal record (5d hit, n) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for bid in ids:
        b = _bk(out, bid)
        if not b:
            continue
        c = b["composite_components"]
        top = ""
        if b.get("contributors") and (b["contributors"]["top"] or b["contributors"]["bottom"]):
            t = max(b["contributors"]["top"] + b["contributors"]["bottom"], key=lambda x: abs(x["contrib"]))
            share = t["share_of_move"]
            top = f"{t['name'][:18]} {pct(t['ret'])}" + (f" ({share * 100:.0f}% of move)" if share is not None and 0 < share < 5 else "")
        lines.append(f"| {_label(b)} | {num(b['composite'])} | {pct(b['residual_5d'])} ({num(c.get('residual_5d_z'))}) | "
                     f"{num(b['turnover_share_z'])} {b['turnover_quadrant'] or ''} | {num(b.get('flow_z'))} | "
                     f"{num(b['breadth_change_5d'], 0)}pp | {b['quadrant'] or '–'} | {b['persist_days']} | {top} | {basket_signal(out, b)} |")
    return lines


def scorecard_lines(out: dict) -> list[str]:
    sc = out.get("scorecard", {})
    if not sc.get("by_signal"):
        return []
    mkts = [m for m in list(MARKETS) + ["GLOBAL"] if any(r["market"] == m for r in sc.get("by_signal_market", []))]
    head = "| Signal | All | " + " | ".join("Themes" if m == "GLOBAL" else m for m in mkts) + " |"
    lines = ["**Signal scorecard** — 5-day hit rate and n, last two years; below 50% = unconfirmed signal", "", head,
             "|" + "---|" * (len(mkts) + 2)]
    for r in sc["by_signal"]:
        cells = [record(next((x for x in sc["by_signal_market"] if x["signal"] == r["signal"] and x["market"] == m), None)) for m in mkts]
        lines.append(f"| {SIGNAL_NAMES.get(r['signal'], r['signal'])} | {record(r)} | " + " | ".join(cells) + " |")
    return lines


def flows_section(out: dict) -> list[str]:
    mf = out.get("market_flows", {})
    lines = []
    if "KR" in mf:
        inv = mf["KR"]["investors"]
        lines.append(f"- **Korea** ({mf['KR']['as_of']}): foreign {money(inv['foreign']['d1'], 'KRW')} 1d / {money(inv['foreign']['d5'], 'KRW')} 5d (z {num(inv['foreign']['z5'])}); "
                     f"institutions {money(inv['inst']['d1'], 'KRW')} 1d / {money(inv['inst']['d5'], 'KRW')} 5d; retail {money(inv['retail']['d1'], 'KRW')} 1d")
    if "HK" in mf:
        inv = mf["HK"]["investors"]["southbound_net"]
        tops = mf["HK"].get("top_stocks_latest", {})
        buyers = ", ".join(f"{x['name']} ({money(x['net'], 'HKD')})" for x in tops.get("buyers", [])[:3])
        sellers = ", ".join(f"{x['name']} ({money(x['net'], 'HKD')})" for x in tops.get("sellers", [])[:3])
        lines.append(f"- **Hong Kong Southbound** ({mf['HK']['as_of']}): net {money(inv['d1'], 'HKD')} 1d / {money(inv['d5'], 'HKD')} 5d (z {num(inv['z5'])}). "
                     f"Top-10 buying: {buyers}. Selling: {sellers}.")
    if "TW" in mf:
        inv = mf["TW"]["investors"]
        lines.append(f"- **Taiwan** ({mf['TW']['as_of']}): foreign {money(inv['foreign']['d1'], 'TWD')} 1d / {money(inv['foreign']['d5'], 'TWD')} 5d (z {num(inv['foreign']['z5'])}); "
                     f"investment trusts {money(inv['trust']['d1'], 'TWD')} 1d")
    if "JP" in mf:
        l = mf["JP"]["latest"]
        lines.append(f"- **Japan** (week to {mf['JP']['as_of']}, TSE Prime): foreigners {money(l.get('foreigners'), 'JPY')}, "
                     f"individuals {money(l.get('individuals'), 'JPY')}, investment trusts {money(l.get('investment_trusts'), 'JPY')}")
    # sector-level flow leaders
    fl = [b for b in out["baskets"] if b["type"] == "sector" and b.get("flow_z") is not None]
    if fl:
        fl = sorted(fl, key=lambda b: b["flow_z"], reverse=True)
        lines.append("- Sector flow z (5d, foreign+institutional / Southbound): strongest " +
                     ", ".join(f"{MARKETS[b['market']]['name']} {b['name']} {num(b['flow_z'])}" for b in fl[:4]) +
                     "; weakest " + ", ".join(f"{MARKETS[b['market']]['name']} {b['name']} {num(b['flow_z'])}" for b in fl[-4:][::-1]))
    return lines or ["- No flow data available."]


def themes_table(out: dict, run: str) -> list[str]:
    lines = ["| Theme | 1d USD | 5d USD | Resid 5d | RRG | US | KR | JP | TW | HK | Lead-lag |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for th in sorted(out["themes"], key=lambda t: (t["total"].get("composite") or -9), reverse=True):
        t = th["total"]
        cells = []
        for c in ("US", "KR", "JP", "TW", "HK"):
            cb = th["countries"].get(c)
            cells.append(pct(cb["ret_1d_usd"]) if cb else "·")
        ll = ""
        if th.get("leadlag"):
            parts = []
            for c, v in th["leadlag"].items():
                if v["mode"] == "implied" and v["implied_asia_ret"] is not None:
                    parts.append(f"{c} implied {pct(v['implied_asia_ret'])} (β {v['slope']})")
                elif v["mode"] == "realised" and v["realised_asia_ret"] is not None:
                    parts.append(f"{c} {pct(v['realised_asia_ret'])} vs implied {pct(v['implied_asia_ret'])}")
            ll = "; ".join(parts[:3])
        lines.append(f"| {th['name']} | {pct(t['ret_1d_usd'])} | {pct(t['ret_5d_usd'])} | {pct(t['residual_5d'])} | {t['quadrant'] or '–'} ({t['persist_days']}d) | "
                     + " | ".join(cells) + f" | {ll} |")
    return lines


def thesis_lines(out: dict) -> list[str]:
    th = out.get("theses") or []
    lines = ["**Thesis tracker** (opened by the pipeline on composite crossings / RRG entries with breadth)", ""]
    if not th:
        return lines + ["- No open theses."]
    lines += ["| Thesis | Direction | Opened | Days | Status | Since-open residual | Trigger |", "|---|---|---|---|---|---|---|"]
    for t in th:
        label = f"{MARKETS[t['market']]['name']} · {t['name']}" if t["market"] in MARKETS else f"{t['name']} (theme)"
        lines.append(f"| {label} | {'rotating in' if t['direction'] == 1 else 'rotating out'} | {t['opened']} | {t['days_open']} | "
                     f"{t['status']} | {pct(t.get('since_open_residual'))} | {t['trigger']} |")
    closed = out.get("theses_closed_recent") or []
    if closed:
        lines += ["", "Closed this week: " + "; ".join(f"{t['name']} ({t['market']}, {t['close_reason']}, {pct(t.get('since_open_residual'))})" for t in closed[:6])]
    return lines


def watch_section(out: dict) -> list[str]:
    lines = []
    for t in out.get("transitions", []):
        lines.append(f"- RRG transition: **{t['name']}** ({t['market']}) {t['from']} → **{t['to']}**")
    for p in out.get("persistence_milestones", []):
        lines.append(f"- Persistence: **{p['name']}** ({p['market']}) {p['quadrant']} for {p['days']} days")
    return lines or ["- No quadrant transitions or milestones today."]


def events_section(out: dict) -> list[str]:
    ev = out.get("events", [])
    near = [e for e in ev if e["kind"] in ("event", "holiday")]
    lines = [f"- {e['date']} · {e['market']} · {e['label']}" for e in near] or ["- No scheduled events or holidays in the next two sessions."]
    lines += [f"- Next scheduled: {e['date']} · {e['market']} · {e['label']}" for e in ev if e["kind"] == "next"]
    lines += [f"- Season ({e['status']}, {e['start']} → {e['end']}): {e['label']}" for e in ev if e["kind"] == "season"]
    ea = out.get("earnings") or {}
    if ea.get("by_sector"):
        more = f" (largest {ea['shown']} of {ea['count']} shown)" if ea["count"] > ea["shown"] else ""
        lines += ["", f"**US earnings, {' and '.join(ea['sessions'])}**{more}:"]
        for sec, names in ea["by_sector"].items():
            lines.append(f"- {sec}: " + ", ".join(f"{x['name']} ({x['ticker']}, {x['date'][5:]}{' ' + x['time'] if x['time'] else ''})" for x in names))
    elif ea.get("sessions"):
        why = ea.get("note") or "none in the cache"
        lines.append(f"- US earnings {' and '.join(ea['sessions'])}: {why}.")
    lines.append("")
    lines.append("- Korea / Taiwan / Japan / Hong Kong single-name earnings dates are not tracked (Yahoo data unreliable); see the season windows above.")
    return lines


def digest_markdown(out: dict, run: str) -> str:
    title = "Asia close" if run == "asia" else "US close"
    as_of = out["meta"]["as_of"]
    stamp = max(as_of.values())
    parts = [f"# Market Rotation Watch — {title} digest, {stamp}", ""]
    parts += ["## 1. Regime", ""] + regime_lines(out, run) + [""]
    sc = scorecard_lines(out)
    if sc:
        parts += sc + [""]
    parts += ["## 2. Rotation leaders and laggards (composite score)", ""]
    parts += movers_table(out, out["leaders"][:6], "Capital rotating IN") + excluded_line(out.get("leaders_flagged", [])) + [""]
    parts += movers_table(out, out["laggards"][:6], "Capital rotating OUT") + excluded_line(out.get("laggards_flagged", [])) + [""]
    parts += ["## 3. Flows", ""] + flows_section(out) + [""]
    parts += ["## 4. Themes across markets (USD)", ""] + themes_table(out, run) + [""]
    parts += ["## 5. Watch list", ""] + watch_section(out) + [""] + thesis_lines(out) + [""]
    parts += ["## 6. Events", ""] + events_section(out) + [""]
    src = out["meta"].get("sources", {})
    counts = out["meta"].get("universe_counts", {})
    if counts:
        names = out["meta"].get("universe_names", {})
        parts += ["_Universe: " + ", ".join(f"{m} {names.get(m, m)} {n}" for m, n in counts.items()) + "._", ""]
    hk = out.get("market_flows", {}).get("HK")
    if hk:
        cov = [b.get("flow_coverage") for b in out["baskets"] if b["type"] == "sector" and b["market"] == "HK" and b.get("flow_coverage") is not None]
        parts += [f"_Data note: Hong Kong sector flows see only the daily Southbound top-10 stocks per channel (latest {hk['as_of']}; "
                  f"{sum(cov)} of {sum(b['n'] for b in out['baskets'] if b['type'] == 'sector' and b['market'] == 'HK')} sector constituents covered on the last day); "
                  "absence from the list counts as zero._", ""]
    if src:
        stale = [k for k, v in src.get("flows", {}).items() if isinstance(v, dict) and not v.get("ok", True)]
        if stale:
            parts += [f"_Data note: flow sources not updated this run: {', '.join(stale)} (showing last good data)._", ""]
        prices = src.get("prices", {})
        if isinstance(prices, dict):
            bad = [k for k, v in prices.items() if isinstance(v, dict) and (v.get("error") or not v.get("updated", True))]
            if prices.get("error"):
                bad = ["all markets"]
            bad = ["benchmarks/FX/theme extras" if b == "XTRA" else b for b in bad]
            if bad:
                parts += [f"_Data note: prices not updated for {', '.join(bad)} (signals computed on the last stored close)._", ""]
    return "\n".join(parts)


def telegram_text(out: dict, run: str, narrative: str | None) -> str:
    title = "Asia close" if run == "asia" else "US close"
    stamp = max(out["meta"]["as_of"].values())
    lines = [f"📊 Market Rotation Watch — {title} · {stamp}", ""]
    if narrative:
        lines += [narrative.strip(), ""]
    lines.append("Regime:")
    for m in (["US"] + ASIA_MARKETS if run == "us" else ASIA_MARKETS + ["US"]):
        r = out["regime"].get(m)
        if r:
            lines.append(f"• {MARKETS[m]['name']} {pct(r['bench_ret_1d'])} · disp z {num(r['dispersion_z'], 1)} · {r['label']}")
    lines.append("")
    lines.append("Rotating in:")
    for bid in out["leaders"][:5]:
        b = _bk(out, bid)
        lines.append(f"• {_label(b)} {num(b['composite'], 1)} · resid5d {pct(b['residual_5d'])} · turn z {num(b['turnover_share_z'], 1)} · {b['quadrant']} {b['persist_days']}d")
    lines.append("Rotating out:")
    for bid in out["laggards"][:5]:
        b = _bk(out, bid)
        lines.append(f"• {_label(b)} {num(b['composite'], 1)} · resid5d {pct(b['residual_5d'])} · turn z {num(b['turnover_share_z'], 1)} · {b['quadrant']} {b['persist_days']}d")
    tr = out.get("transitions", [])
    if tr:
        lines += ["", "RRG transitions: " + "; ".join(f"{t['name']} ({t['market']}) → {t['to']}" for t in tr[:6])]
    return "\n".join(lines)
