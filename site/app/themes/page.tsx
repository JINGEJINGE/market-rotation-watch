"use client";
import { useState } from "react";
import { useLatest, MARKET_NAMES, pct, num, fmt, sign } from "@/lib/data";
import { RRG, Sparkline } from "@/components/charts";
import { BasketTable, Contributors, Quadrant } from "@/components/tables";

export default function Themes() {
  const { data, error } = useLatest();
  const [sel, setSel] = useState<string | null>(null);
  if (error) return <div className="loading">Could not load data: {error}</div>;
  if (!data) return <div className="loading">Loading…</div>;
  const themes = [...data.themes].sort((a, b) => (b.total.composite ?? -9) - (a.total.composite ?? -9));
  const th = themes.find((t) => t.id === sel) ?? themes[0];
  return (
    <>
      <h1>Themes <span className="note" style={{ fontWeight: 400 }}>· cross-market baskets, USD, vs ACWI</span></h1>
      <div className="card"><RRG baskets={themes.map((t) => t.total)} height={420} /></div>

      <h2>All themes</h2>
      <div className="card" style={{ overflowX: "auto" }}>
        <table>
          <thead><tr><th>Theme</th><th className="num">Score</th><th className="num">1d USD</th><th className="num">5d USD</th><th className="num">20d USD</th><th className="num">β-adj resid 5d</th><th className="num">Turnover z</th><th>RRG</th>{["US", "KR", "JP", "TW", "HK"].map((c) => <th key={c} className="num">{c} 1d</th>)}<th>Rel 120d</th></tr></thead>
          <tbody>
            {themes.map((t) => (
              <tr key={t.id} onClick={() => setSel(t.id)} style={{ cursor: "pointer", fontWeight: t.id === th?.id ? 600 : 400 }}>
                <td>{t.name} <span className="note">{t.total.n}</span></td>
                <td className={`num ${sign(t.total.composite)}`}>{num(t.total.composite, 1)}</td>
                <td className={`num ${sign(t.total.ret_1d_usd)}`}>{pct(t.total.ret_1d_usd)}</td>
                <td className={`num ${sign(t.total.ret_5d_usd)}`}>{pct(t.total.ret_5d_usd)}</td>
                <td className={`num ${sign(t.total.ret_20d_usd)}`}>{pct(t.total.ret_20d_usd)}</td>
                <td className={`num ${sign(t.total.residual_5d)}`}>{pct(t.total.residual_5d)}</td>
                <td className={`num ${sign(t.total.turnover_share_z)}`}>{num(t.total.turnover_share_z, 1)}</td>
                <td><Quadrant q={t.total.quadrant} /> <span className="note">{t.total.persist_days}d</span></td>
                {["US", "KR", "JP", "TW", "HK"].map((c) => { const cb = t.countries[c]; return <td key={c} className={`num ${sign(cb?.ret_1d_usd)}`}>{cb ? pct(cb.ret_1d_usd) : <span className="note">·</span>}</td>; })}
                <td><Sparkline values={t.total.series.rel_index_120d} base={100} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {th && (
        <>
          <h2>{th.name} <span className="note" style={{ fontWeight: 400 }}>· {th.description}</span></h2>
          <BasketTable baskets={Object.values(th.countries)} showMarket usd />
          <div className="grid two" style={{ marginTop: 14 }}>
            <div className="card">
              <h3>Lead-lag: US session → next Asia session (USD)</h3>
              {!th.leadlag && <p className="note">No US members in this theme, so no overnight transmission is computed.</p>}
              {th.leadlag && (
                <table>
                  <thead><tr><th>Country</th><th className="num">US ret</th><th className="num">β (60d)</th><th className="num">corr</th><th className="num">Implied</th><th className="num">Realised</th><th className="num">Surprise</th></tr></thead>
                  <tbody>
                    {Object.entries(th.leadlag).map(([c, v]: any) => (
                      <tr key={c}><td><span className={`dot m-${c}`} />{MARKET_NAMES[c]} <span className="note">{v.mode === "implied" ? `next session after US ${v.us_date}` : `session ${v.asia_date}`}</span></td>
                        <td className={`num ${sign(v.us_ret)}`}>{pct(v.us_ret)}</td><td className="num">{fmt(v.slope, 2)}</td><td className="num">{fmt(v.corr, 2)}</td>
                        <td className={`num ${sign(v.implied_asia_ret)}`}>{pct(v.implied_asia_ret)}</td><td className={`num ${sign(v.realised_asia_ret)}`}>{pct(v.realised_asia_ret)}</td><td className={`num ${sign(v.surprise)}`}>{pct(v.surprise)}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="note">β is the rolling 60-session regression of the country basket's next-session USD return on the US members' USD return. "Implied" = β × latest US move; "surprise" = realised minus implied.</p>
            </div>
            <div className="card">
              <h3>Contributors (cross-market, USD)</h3>
              <Contributors b={th.total} />
              <p className="note">Members: {th.total.tickers.join(", ")}</p>
            </div>
          </div>
        </>
      )}
    </>
  );
}
