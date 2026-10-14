"use client";
import { useLatest, MARKET_NAMES, pct, sign } from "@/lib/data";

const NAMES: Record<string, string> = { rrg_leading_entry: "RRG: entered Leading", rrg_improving_entry: "RRG: Lagging → Improving", composite_above: "Composite ≥ +1.5", composite_below: "Composite ≤ −1.5 (sign flipped)" };

export default function Scorecard() {
  const { data, error } = useLatest();
  if (error) return <div className="loading">Could not load data: {error}</div>;
  if (!data) return <div className="loading">Loading…</div>;
  const sc = data.scorecard;
  const row = (r: any, i: number) => (
    <tr key={i}><td>{NAMES[r.signal] ?? r.signal}{r.market ? <> · <span className={`dot m-${r.market}`} />{MARKET_NAMES[r.market]}</> : ""}</td><td className="num">{r.n}</td><td className="num">{(r.hit_5d * 100).toFixed(0)}%</td><td className={`num ${sign(r.avg_5d)}`}>{pct(r.avg_5d, 2)}</td><td className="num">{(r.hit_20d * 100).toFixed(0)}%</td><td className={`num ${sign(r.avg_20d)}`}>{pct(r.avg_20d, 2)}</td></tr>
  );
  return (
    <>
      <h1>Signal scorecard <span className="note" style={{ fontWeight: 400 }}>· {sc?.window}</span></h1>
      <p className="note">Every signal event in the last two years, followed by the basket's beta-adjusted relative return over the next 5 and 20 sessions. Hit rate = share of events with a positive forward residual. Backfilled from history on day one; accumulates from live runs. Current constituents applied to history (mild survivorship bias).</p>
      {sc?.by_signal?.length ? (
        <div className="grid two">
          <div className="card"><h3>By signal</h3><table><thead><tr><th>Signal</th><th className="num">n</th><th className="num">Hit 5d</th><th className="num">Avg 5d</th><th className="num">Hit 20d</th><th className="num">Avg 20d</th></tr></thead><tbody>{sc.by_signal.map(row)}</tbody></table></div>
          <div className="card"><h3>By signal and market</h3><table><thead><tr><th>Signal</th><th className="num">n</th><th className="num">Hit 5d</th><th className="num">Avg 5d</th><th className="num">Hit 20d</th><th className="num">Avg 20d</th></tr></thead><tbody>{sc.by_signal_market.map(row)}</tbody></table></div>
        </div>
      ) : <div className="card"><p className="note">{sc?.note ?? "No events yet."}</p></div>}
      {sc?.recent_events?.length > 0 && (
        <div className="card" style={{ marginTop: 14 }}><h3>Most recent events</h3><table><thead><tr><th>Date</th><th>Signal</th><th>Basket</th><th className="num">Fwd 5d</th><th className="num">Fwd 20d</th></tr></thead>
          <tbody>{[...sc.recent_events].reverse().map((e: any, i: number) => <tr key={i}><td>{e.date}</td><td>{NAMES[e.signal] ?? e.signal}</td><td>{e.basket}</td><td className={`num ${sign(e.fwd5)}`}>{pct(e.fwd5, 2)}</td><td className={`num ${sign(e.fwd20)}`}>{pct(e.fwd20, 2)}</td></tr>)}</tbody></table></div>
      )}
    </>
  );
}
