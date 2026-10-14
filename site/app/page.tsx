"use client";
import { useState } from "react";
import Link from "next/link";
import { useLatest, MARKET_NAMES, pct, num, fmt, sign, Basket } from "@/lib/data";
import { Heatmap, Sparkline } from "@/components/charts";
import { BasketTable, Quadrant } from "@/components/tables";

const METRICS: Record<string, { label: string; fmt: (v: number) => string; lim: number }> = {
  residual_5d_z: { label: "β-adj resid 5d (z)", fmt: (v) => num(v, 1), lim: 2.5 },
  rel_5d_usd: { label: "Rel return 5d (USD)", fmt: (v) => pct(v), lim: 0.05 },
  rel_20d_usd: { label: "Rel return 20d (USD)", fmt: (v) => pct(v), lim: 0.1 },
  turnover_share_z: { label: "Turnover share (z)", fmt: (v) => num(v, 1), lim: 2.5 },
  flow_z: { label: "Flow (z, Asia only)", fmt: (v) => num(v, 1), lim: 2.5 },
  composite: { label: "Composite score", fmt: (v) => num(v, 1), lim: 2.5 },
};

export default function Overview() {
  const { data, error } = useLatest();
  const [metric, setMetric] = useState("residual_5d_z");
  if (error) return <div className="loading">Could not load data: {error}</div>;
  if (!data) return <div className="loading">Loading…</div>;
  const by = Object.fromEntries(data.baskets.map((b) => [b.id, b]));
  const leaders = data.leaders.map((id) => by[id]).filter(Boolean) as Basket[];
  const laggards = data.laggards.map((id) => by[id]).filter(Boolean) as Basket[];
  const m = METRICS[metric];
  const order = data.meta.run === "us" ? ["US", "KR", "JP", "TW", "HK"] : ["KR", "JP", "TW", "HK", "US"];
  return (
    <>
      <h1>Overview <span className="note" style={{ fontWeight: 400 }}>· {data.meta.run === "asia" ? "Asia close" : "US close"} · generated {data.meta.generated_at.slice(0, 16).replace("T", " ")} UTC</span></h1>

      <h2>Regime</h2>
      <div className="regime">
        {order.filter((k) => data.regime[k]).map((k) => {
          const r = data.regime[k];
          return (
            <Link key={k} href={`/markets/${k}/`} className="card">
              <div className="label"><span className={`dot m-${k}`} />{MARKET_NAMES[k]} <span className="note">{r.as_of.slice(5)}</span></div>
              <div><span className={`stat-v ${sign(r.bench_ret_1d)}`} style={{ fontSize: 20, fontWeight: 600 }}>{pct(r.bench_ret_1d)}</span> <span className="note">{r.benchmark} · 5d {pct(r.bench_ret_5d)}{k !== "US" && r.fx_ret_5d != null ? ` · FX ${pct(r.fx_ret_5d)}` : ""}</span></div>
              <div className="verdict">{r.label}</div>
              <div className="note" style={{ marginTop: 4 }}>dispersion z {num(r.dispersion_z, 1)} · corr pctile {fmt(r.avg_corr_pctile, 2)} · breadth {fmt(r.breadth_pct_above_20, 0)}% &gt;20DMA · EW–CW 5d {pct(r.ew_cw_gap_5d)}</div>
              <div style={{ marginTop: 4 }}><span className="note">dispersion 60d </span><Sparkline values={r.dispersion_series_60d} width={120} /></div>
            </Link>
          );
        })}
      </div>

      {data.digest?.narrative && (
        <>
          <h2>Today's read</h2>
          <div className="card" style={{ maxWidth: 900, whiteSpace: "pre-wrap" }}>{data.digest.narrative}</div>
        </>
      )}

      <h2>Cross-market heatmap</h2>
      <div className="controls">
        {Object.entries(METRICS).map(([k, v]) => <button key={k} className={`seg ${metric === k ? "on" : ""}`} onClick={() => setMetric(k)}>{v.label}</button>)}
      </div>
      <div className="card" style={{ overflowX: "auto" }}>
        <Heatmap sectors={data.heatmap.sectors} markets={data.heatmap.markets} values={data.heatmap.values[metric]} fmtFn={m.fmt} lim={m.lim} />
        <p className="note">Harmonised 11-sector scheme. Warm = capital rotating in, cool = rotating out. Cap-weighted; relative to each market's own benchmark.</p>
      </div>

      <h2>Rotating in</h2>
      <BasketTable baskets={leaders} />
      <h2>Rotating out</h2>
      <BasketTable baskets={laggards} />

      <div className="grid two" style={{ marginTop: 14 }}>
        <div className="card">
          <h3>RRG transitions today</h3>
          {data.transitions.length === 0 && <p className="note">None.</p>}
          {data.transitions.map((t) => <div key={t.id} className="small"><span className={`dot m-${t.market}`} />{t.name} <span className="note">{t.market}</span> · <Quadrant q={t.from} /> → <Quadrant q={t.to} /></div>)}
          <h3 style={{ marginTop: 14 }}>Persistence milestones</h3>
          {data.persistence_milestones.length === 0 && <p className="note">None.</p>}
          {data.persistence_milestones.map((p) => <div key={p.id} className="small"><span className={`dot m-${p.market}`} />{p.name} · <Quadrant q={p.quadrant} /> {p.days} days</div>)}
        </div>
        <div className="card">
          <h3>Events, next sessions</h3>
          {data.events.length === 0 && <p className="note">Nothing scheduled.</p>}
          {data.events.map((e, i) => <div key={i} className="small"><span className="note">{e.date ?? "ongoing"}</span> · {e.market} · {e.label}</div>)}
          <h3 style={{ marginTop: 14 }}>Data freshness</h3>
          <div className="small">{Object.entries(data.meta.as_of).map(([k, v]) => <span key={k} style={{ marginRight: 10 }}><span className={`dot m-${k}`} />{v}</span>)}</div>
          {data.meta.sources?.flows && <div className="note" style={{ marginTop: 4 }}>Flows: {Object.entries(data.meta.sources.flows).map(([k, v]: any) => `${k} ${v.ok ? "ok" : "stale"}${v.last_date ? ` (${v.last_date})` : ""}`).join(" · ")}</div>}
        </div>
      </div>
    </>
  );
}
