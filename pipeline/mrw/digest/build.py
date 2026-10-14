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


def movers_table(out: dict, ids: list[str], title: str) -> list[str]:
    lines = [f"**{title}**", "", "| Basket | Score | Resid 5d (z) | Turnover z | Flow z | Breadth Δ5d | RRG | Days | Top contributor |",
             "|---|---|---|---|---|---|---|---|---|"]
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
                     f"{num(b['breadth_change_5d'], 0)}pp | {b['quadrant'] or '–'} | {b['persist_days']} | {top} |")
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


def watch_section(out: dict) -> list[str]:
    lines = []
    for t in out.get("transitions", []):
        lines.append(f"- RRG transition: **{t['name']}** ({t['market']}) {t['from']} → **{t['to']}**")
    for p in out.get("persistence_milestones", []):
        lines.append(f"- Persistence: **{p['name']}** ({p['market']}) {p['quadrant']} for {p['days']} days")
    return lines or ["- No quadrant transitions or milestones today."]


def events_section(out: dict) -> list[str]:
    ev = out.get("events", [])
    return [f"- {e['date'] or 'ongoing'} · {e['market']} · {e['label']}" for e in ev] or ["- Nothing scheduled in the next few sessions."]


def digest_markdown(out: dict, run: str) -> str:
    title = "Asia close" if run == "asia" else "US close"
    as_of = out["meta"]["as_of"]
    stamp = max(as_of.values())
    parts = [f"# Market Rotation Watch — {title} digest, {stamp}", ""]
    parts += ["## 1. Regime", ""] + regime_lines(out, run) + [""]
    parts += ["## 2. Rotation leaders and laggards (composite score)", ""]
    parts += movers_table(out, out["leaders"][:6], "Capital rotating IN") + [""]
    parts += movers_table(out, out["laggards"][:6], "Capital rotating OUT") + [""]
    parts += ["## 3. Flows", ""] + flows_section(out) + [""]
    parts += ["## 4. Themes across markets (USD)", ""] + themes_table(out, run) + [""]
    parts += ["## 5. Watch list", ""] + watch_section(out) + [""]
    parts += ["## 6. Events", ""] + events_section(out) + [""]
    src = out["meta"].get("sources", {})
    if src:
        stale = [k for k, v in src.get("flows", {}).items() if isinstance(v, dict) and not v.get("ok", True)]
        if stale:
            parts += [f"_Data note: flow sources not updated this run: {', '.join(stale)} (showing last good data)._", ""]
        prices = src.get("prices", {})
        if isinstance(prices, dict):
            bad = [k for k, v in prices.items() if isinstance(v, dict) and (v.get("error") or not v.get("updated", True))]
            if prices.get("error"):
                bad = ["all markets"]
            if bad:
                parts += [f"_Data note: prices not updated this run for {', '.join(bad)} (signals computed on the last stored close)._", ""]
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
