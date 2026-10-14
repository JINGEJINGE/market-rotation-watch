"use client";
import { useLatest, MARKET_NAMES, num, money, sign } from "@/lib/data";
import { BarList, Sparkline } from "@/components/charts";

const CCY: Record<string, string> = { KR: "KRW", TW: "TWD", HK: "HKD", JP: "JPY" };

export default function Flows() {
  const { data, error } = useLatest();
  if (error) return <div className="loading">Could not load data: {error}</div>;
  if (!data) return <div className="loading">Loading…</div>;
  const mf = data.market_flows ?? {};
  const secs = (m: string) => data.baskets.filter((b) => b.type === "sector" && b.market === m && b.flow_5d != null).sort((a, b) => (b.flow_5d ?? 0) - (a.flow_5d ?? 0));
  const thm = (m: string) => data.baskets.filter((b) => b.type === "theme_country" && b.country === m && b.flow_5d != null).sort((a, b) => (b.flow_5d ?? 0) - (a.flow_5d ?? 0));
  return (
    <>
      <h1>Investor-type flows <span className="note" style={{ fontWeight: 400 }}>· Korea (Naver, daily) · Hong Kong Southbound (HKEX, daily) · Taiwan (TWSE, daily) · Japan (JPX, weekly)</span></h1>
      {["KR", "TW", "HK", "JP"].map((m) => {
        const f = mf[m];
        if (!f) return <div key={m} className="card" style={{ marginTop: 14 }}><h3><span className={`dot m-${m}`} />{MARKET_NAMES[m]}</h3><p className="note">No flow data yet.</p></div>;
        const ccy = CCY[m];
        return (
          <div key={m} style={{ marginTop: 18 }}>
            <h2><span className={`dot m-${m}`} />{MARKET_NAMES[m]} <span className="note" style={{ fontWeight: 400 }}>· as of {f.as_of} · {ccy}{f.note ? ` · ${f.note}` : ""}</span></h2>
            <div className="grid three">
              <div className="card">
                <h3>Market level</h3>
                {f.frequency === "weekly" ? (
                  <>
                    <BarList rows={Object.entries(f.latest).map(([k, v]) => ({ label: k.replace("_", " "), value: v as number }))} unit={(v) => money(v, ccy)} />
                    <table style={{ marginTop: 10 }}><thead><tr><th>Week</th><th className="num">Foreigners</th><th className="num">Individuals</th><th className="num">Inv. trusts</th></tr></thead>
                      <tbody>{[...f.series].reverse().map((w: any) => <tr key={w.week_end}><td>{w.week_end}</td><td className={`num ${sign(w.foreigners)}`}>{money(w.foreigners, ccy)}</td><td className={`num ${sign(w.individuals)}`}>{money(w.individuals, ccy)}</td><td className={`num ${sign(w.investment_trusts)}`}>{money(w.investment_trusts, ccy)}</td></tr>)}</tbody></table>
                  </>
                ) : (
                  <table>
                    <thead><tr><th>Investor</th><th className="num">1d</th><th className="num">5d</th><th className="num">20d</th><th className="num">5d z</th><th>20d</th></tr></thead>
                    <tbody>{Object.entries(f.investors).map(([k, v]: any) => <tr key={k}><td>{k}</td><td className={`num ${sign(v.d1)}`}>{money(v.d1, ccy)}</td><td className={`num ${sign(v.d5)}`}>{money(v.d5, ccy)}</td><td className={`num ${sign(v.d20)}`}>{money(v.d20, ccy)}</td><td className={`num ${sign(v.z5)}`}>{num(v.z5, 1)}</td><td><Sparkline values={v.series_20d.map((x: any) => x.v)} base={0} /></td></tr>)}</tbody>
                  </table>
                )}
                {f.top_stocks_latest && <div className="small" style={{ marginTop: 8 }}><b>Top-10 buyers {f.top_stocks_latest.date}:</b> {f.top_stocks_latest.buyers.map((x: any) => `${x.name} ${money(x.net, "HKD")}`).join(", ")}<br /><b>Sellers:</b> {f.top_stocks_latest.sellers.map((x: any) => `${x.name} ${money(x.net, "HKD")}`).join(", ")}</div>}
              </div>
              {f.frequency !== "weekly" && (
                <>
                  <div className="card"><h3>By sector, 5d</h3><BarList rows={secs(m).map((s) => ({ label: s.name, value: s.flow_5d, sub: s.flow_z != null ? `z ${num(s.flow_z, 1)}` : "" }))} unit={(v) => money(v, ccy)} /></div>
                  <div className="card"><h3>By theme, 5d</h3><BarList rows={thm(m).map((s) => ({ label: s.name.split(" — ")[0], value: s.flow_5d, sub: s.flow_z != null ? `z ${num(s.flow_z, 1)}` : "" }))} unit={(v) => money(v, ccy)} /></div>
                </>
              )}
            </div>
          </div>
        );
      })}
    </>
  );
}
