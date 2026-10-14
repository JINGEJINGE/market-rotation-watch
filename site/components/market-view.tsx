"use client";
import { useState } from "react";
import { useLatest, MARKET_NAMES, pct, num, fmt, sign, money } from "@/lib/data";
import { RRG, Sparkline, BarList } from "@/components/charts";
import { BasketTable, Contributors } from "@/components/tables";

const CCY: Record<string, string> = { KR: "KRW", TW: "TWD", HK: "HKD", JP: "JPY", US: "USD" };

export function MarketView({ mkt }: { mkt: string }) {
  const { data, error } = useLatest();
  const [sel, setSel] = useState<string | null>(null);
  if (error) return <div className="loading">Could not load data: {error}</div>;
  if (!data) return <div className="loading">Loading…</div>;
  const r = data.regime[mkt];
  const sectors = data.baskets.filter((b) => b.type === "sector" && b.market === mkt).sort((a, b) => (b.composite ?? -9) - (a.composite ?? -9));
  const themes = data.baskets.filter((b) => b.type === "theme_country" && b.country === mkt).sort((a, b) => (b.composite ?? -9) - (a.composite ?? -9));
  const selected = data.baskets.find((b) => b.id === sel) ?? sectors[0];
  const flows = data.market_flows?.[mkt];
  const ccy = CCY[mkt];
  const quadrants: Record<string, string[]> = {};
  for (const s of sectors) if (s.turnover_quadrant) (quadrants[s.turnover_quadrant] ??= []).push(s.name);
  return (
    <>
      <h1><span className={`dot m-${mkt}`} />{MARKET_NAMES[mkt]} <span className="note" style={{ fontWeight: 400 }}>· {r?.as_of} · {data.meta.universe_counts[mkt]} stocks</span></h1>
      {r && (
        <div className="grid five">
          <div className="card stat"><span className="l">{r.benchmark}</span><span className={`v ${sign(r.bench_ret_1d)}`}>{pct(r.bench_ret_1d)}</span><span className="note">5d {pct(r.bench_ret_5d)} · 20d {pct(r.bench_ret_20d)}{mkt !== "US" ? ` · USD 5d ${pct(r.bench_ret_5d_usd)}` : ""}</span></div>
          <div className="card stat"><span className="l">Regime</span><span className="v" style={{ fontSize: 17 }}>{r.label}</span><span className="note">dispersion z {num(r.dispersion_z, 1)} · corr {fmt(r.avg_corr, 2)} (pctile {fmt(r.avg_corr_pctile, 2)})</span></div>
          <div className="card stat"><span className="l">Breadth</span><span className="v">{fmt(r.breadth_pct_above_20, 0)}%</span><span className="note">&gt;20DMA · {fmt(r.breadth_pct_above_50, 0)}% &gt;50DMA · A/D {r.advancers}/{r.decliners}</span></div>
          <div className="card stat"><span className="l">Equal − cap weight 5d</span><span className={`v ${sign(r.ew_cw_gap_5d)}`}>{pct(r.ew_cw_gap_5d)}</span><span className="note">positive = broad participation; negative = mega-cap led</span></div>
          <div className="card stat"><span className="l">Realised vol 20d</span><span className="v">{r.realised_vol_20d != null ? `${(r.realised_vol_20d * 100).toFixed(0)}%` : "–"}</span><span className="note">dispersion 60d <Sparkline values={r.dispersion_series_60d} width={100} /></span></div>
        </div>
      )}

      <h2>Relative rotation — sectors</h2>
      <div className="card"><RRG baskets={sectors} /></div>

      <h2>Sectors</h2>
      <BasketTable baskets={sectors} showMarket={false} />

      <div className="grid two" style={{ marginTop: 14 }}>
        <div className="card">
          <h3>Price × turnover quadrants (5d)</h3>
          {["Accumulation", "Thin drift", "Distribution", "Apathy"].map((q) => (
            <div key={q} className="small" style={{ margin: "4px 0" }}><b>{q}</b>: {quadrants[q]?.join(", ") || <span className="note">none</span>}</div>
          ))}
          <p className="note">Accumulation = outperforming on rising turnover share. Thin drift = outperforming on falling share (short covering / low conviction). Distribution = underperforming on rising share. Apathy = underperforming, no one trading it.</p>
          <h3 style={{ marginTop: 12 }}>Turnover share z by sector</h3>
          <BarList rows={sectors.map((s) => ({ label: s.name, value: s.turnover_share_z, sub: s.turnover_share != null ? `${(s.turnover_share * 100).toFixed(1)}%` : "" }))} unit={(v) => num(v, 1)} maxAbs={3} />
        </div>
        <div className="card">
          <h3>Contributors</h3>
          <div className="controls">
            <select value={selected?.id} onChange={(e) => setSel(e.target.value)}>{[...sectors, ...themes].map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
          </div>
          {selected && <Contributors b={selected} />}
          {selected && <p className="note">Equal-weight 1d {pct(selected.ew_ret_1d)} vs cap-weight {pct(selected.ret_1d)}. Beta {fmt(selected.beta, 2)}.</p>}
        </div>
      </div>

      {flows && (
        <>
          <h2>Investor-type flows</h2>
          <div className="grid two">
            <div className="card">
              <h3>Market level · {flows.as_of} · {ccy}</h3>
              {flows.frequency === "weekly" ? (
                <BarList rows={Object.entries(flows.latest).map(([k, v]) => ({ label: k.replace("_", " "), value: v as number }))} unit={(v) => money(v, ccy)} />
              ) : (
                <table>
                  <thead><tr><th>Investor</th><th className="num">1d</th><th className="num">5d</th><th className="num">20d</th><th className="num">5d z</th><th>20d</th></tr></thead>
                  <tbody>
                    {Object.entries(flows.investors).map(([k, v]: any) => (
                      <tr key={k}><td>{k}</td><td className={`num ${sign(v.d1)}`}>{money(v.d1, ccy)}</td><td className={`num ${sign(v.d5)}`}>{money(v.d5, ccy)}</td><td className={`num ${sign(v.d20)}`}>{money(v.d20, ccy)}</td><td className={`num ${sign(v.z5)}`}>{num(v.z5, 1)}</td><td><Sparkline values={v.series_20d.map((x: any) => x.v)} base={0} /></td></tr>
                    ))}
                  </tbody>
                </table>
              )}
              {flows.note && <p className="note">{flows.note}</p>}
              {flows.top_stocks_latest && (
                <div className="small" style={{ marginTop: 8 }}>
                  <b>Top-10 Southbound buyers:</b> {flows.top_stocks_latest.buyers.map((x: any) => `${x.name} ${money(x.net, "HKD")}`).join(", ")}<br />
                  <b>Sellers:</b> {flows.top_stocks_latest.sellers.map((x: any) => `${x.name} ${money(x.net, "HKD")}`).join(", ")}
                </div>
              )}
            </div>
            <div className="card">
              <h3>Sector flow, 5d ({mkt === "HK" ? "Southbound top-10 coverage only" : mkt === "KR" ? "foreign + institutional" : "foreign + investment trust"})</h3>
              <BarList rows={sectors.filter((s) => s.flow_5d != null).sort((a, b) => (b.flow_5d ?? 0) - (a.flow_5d ?? 0)).map((s) => ({ label: s.name, value: s.flow_5d, sub: s.flow_z != null ? `z ${num(s.flow_z, 1)}` : "" }))} unit={(v) => money(v, ccy)} />
            </div>
          </div>
        </>
      )}

      {themes.length > 0 && (
        <>
          <h2>Theme members listed here</h2>
          <BasketTable baskets={themes} showMarket={false} />
        </>
      )}
    </>
  );
}
