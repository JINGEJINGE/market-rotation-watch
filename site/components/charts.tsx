"use client";
import { Fragment, useState } from "react";
import { Basket, MARKET_NAMES, num, pct, sign } from "@/lib/data";

const MC: Record<string, string> = { US: "var(--us)", KR: "var(--kr)", HK: "var(--hk)", JP: "var(--jp)", TW: "var(--tw)", GLOBAL: "var(--global)" };

export function Sparkline({ values, width = 90, height = 22, base }: { values: (number | null)[]; width?: number; height?: number; base?: number }) {
  const v = values.filter((x): x is number => x != null);
  if (v.length < 2) return <span className="note">–</span>;
  const min = Math.min(...v, base ?? Infinity), max = Math.max(...v, base ?? -Infinity);
  const sx = (i: number) => (i / (v.length - 1)) * (width - 2) + 1;
  const sy = (y: number) => height - 2 - ((y - min) / (max - min || 1)) * (height - 4);
  const d = v.map((y, i) => `${i === 0 ? "M" : "L"}${sx(i).toFixed(1)},${sy(y).toFixed(1)}`).join(" ");
  const up = v[v.length - 1] >= v[0];
  return (
    <svg className="sparkline" width={width} height={height} aria-label="trend">
      {base != null && <line x1={1} x2={width - 1} y1={sy(base)} y2={sy(base)} stroke="var(--axis)" strokeDasharray="2 2" />}
      <path d={d} fill="none" stroke={up ? "var(--pos)" : "var(--neg)"} strokeWidth={1.5} />
    </svg>
  );
}

export function RRG({ baskets, height = 440, labelFn }: { baskets: Basket[]; height?: number; labelFn?: (b: Basket) => string }) {
  const [hover, setHover] = useState<{ b: Basket; x: number; y: number } | null>(null);
  const bs = baskets.filter((b) => b.rs_ratio != null && b.rs_mom != null);
  const W = 760, H = height, pad = 36;
  const lx = Math.max(1.6, ...bs.map((b) => Math.abs(b.rs_ratio! - 100))) + 0.3;
  const ly = Math.max(1.6, ...bs.map((b) => Math.abs(b.rs_mom! - 100))) + 0.3;
  const X = (v: number) => pad + ((v - (100 - lx)) / (2 * lx)) * (W - 2 * pad);
  const Y = (v: number) => H - pad - ((v - (100 - ly)) / (2 * ly)) * (H - 2 * pad);
  return (
    <div style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxHeight: H }} role="img" aria-label="Relative rotation graph">
        <rect x={pad} y={pad} width={(W - 2 * pad) / 2} height={(H - 2 * pad) / 2} fill="var(--pos-soft)" opacity={0.18} />
        <rect x={W / 2} y={pad} width={(W - 2 * pad) / 2} height={(H - 2 * pad) / 2} fill="var(--pos-soft)" opacity={0.35} />
        <rect x={pad} y={H / 2} width={(W - 2 * pad) / 2} height={(H - 2 * pad) / 2} fill="var(--neg-soft)" opacity={0.35} />
        <rect x={W / 2} y={H / 2} width={(W - 2 * pad) / 2} height={(H - 2 * pad) / 2} fill="var(--neg-soft)" opacity={0.18} />
        <line x1={X(100)} x2={X(100)} y1={pad} y2={H - pad} stroke="var(--axis)" />
        <line x1={pad} x2={W - pad} y1={Y(100)} y2={Y(100)} stroke="var(--axis)" />
        {[["Improving", pad + 6, pad + 14, "start"], ["Leading", W - pad - 6, pad + 14, "end"], ["Lagging", pad + 6, H - pad - 6, "start"], ["Weakening", W - pad - 6, H - pad - 6, "end"]].map(([t, x, y, a]) => (
          <text key={t as string} x={x as number} y={y as number} textAnchor={a as "start" | "end"} fontSize={11} fill="var(--muted)">{t}</text>
        ))}
        <text x={W / 2} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--ink-2)">RS-Ratio → relative strength vs own benchmark</text>
        <text x={12} y={H / 2} textAnchor="middle" fontSize={11} fill="var(--ink-2)" transform={`rotate(-90 12 ${H / 2})`}>RS-Momentum ↑</text>
        {bs.map((b) => {
          const tr = b.series.rrg_trail.filter((p) => p[0] != null && p[1] != null);
          const col = MC[b.market] ?? "var(--global)";
          return (
            <g key={b.id} onMouseEnter={(e) => setHover({ b, x: e.clientX, y: e.clientY })} onMouseMove={(e) => setHover({ b, x: e.clientX, y: e.clientY })} onMouseLeave={() => setHover(null)} style={{ cursor: "default" }}>
              {tr.length > 1 && <polyline points={tr.map((p) => `${X(p[0])},${Y(p[1])}`).join(" ")} fill="none" stroke={col} strokeWidth={1.4} opacity={0.5} />}
              <circle cx={X(b.rs_ratio!)} cy={Y(b.rs_mom!)} r={10} fill="transparent" />
              <circle cx={X(b.rs_ratio!)} cy={Y(b.rs_mom!)} r={5} fill={col} stroke="var(--surface)" strokeWidth={1.5} />
              <text x={X(b.rs_ratio!) + 7} y={Y(b.rs_mom!) + 3} fontSize={10} fill="var(--ink-2)">{labelFn ? labelFn(b) : b.name}</text>
            </g>
          );
        })}
      </svg>
      {hover && (
        <div className="tip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
          <b>{hover.b.name}</b> · {MARKET_NAMES[hover.b.market]}<br />
          {hover.b.quadrant} for {hover.b.persist_days}d · RS {hover.b.rs_ratio?.toFixed(2)} / mom {hover.b.rs_mom?.toFixed(2)}<br />
          rel 5d {pct(hover.b.rel_5d)} · resid 5d {pct(hover.b.residual_5d)} · turnover z {num(hover.b.turnover_share_z)}
        </div>
      )}
    </div>
  );
}

export function Heatmap({ sectors, markets, values, fmtFn, lim }: { sectors: string[]; markets: string[]; values: (number | null)[][]; fmtFn: (v: number) => string; lim: number }) {
  const color = (v: number | null) => {
    if (v == null) return "var(--mid)";
    const t = Math.max(-1, Math.min(1, v / lim));
    const a = Math.abs(t);
    return t >= 0 ? `color-mix(in oklab, var(--pos) ${Math.round(a * 85)}%, var(--surface))` : `color-mix(in oklab, var(--neg) ${Math.round(a * 85)}%, var(--surface))`;
  };
  const ink = (v: number | null) => (v != null && Math.abs(v / lim) > 0.6 ? "#fff" : "var(--ink)");
  return (
    <div className="heat" style={{ gridTemplateColumns: `170px repeat(${markets.length}, 1fr)` }}>
      <div />
      {markets.map((m) => <div key={m} className="collabel"><span className={`dot m-${m}`} />{MARKET_NAMES[m]}</div>)}
      {sectors.map((s, i) => (
        <Fragment key={s}>
          <div className="rowlabel">{s}</div>
          {markets.map((m, j) => {
            const v = values[i]?.[j] ?? null;
            return <div key={`${s}${m}`} className="cell" style={{ background: color(v), color: ink(v) }} title={`${s} · ${MARKET_NAMES[m]}`}>{v == null ? "·" : fmtFn(v)}</div>;
          })}
        </Fragment>
      ))}
    </div>
  );
}

export function BarList({ rows, unit, maxAbs }: { rows: { label: string; value: number | null; sub?: string }[]; unit: (v: number) => string; maxAbs?: number }) {
  const m = maxAbs ?? Math.max(1e-9, ...rows.map((r) => Math.abs(r.value ?? 0)));
  return (
    <div className="bars">
      {rows.map((r) => {
        const v = r.value ?? 0;
        const w = (Math.abs(v) / m) * 50;
        return (
          <div className="bar-row" key={r.label}>
            <div title={r.label} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.label}{r.sub && <span className="note"> {r.sub}</span>}</div>
            <div className="bar-track">
              <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "var(--axis)" }} />
              <div className="bar-fill" style={{ left: v >= 0 ? "50%" : `${50 - w}%`, width: `${w}%`, background: v >= 0 ? "var(--pos)" : "var(--neg)" }} />
            </div>
            <div className={`num ${sign(r.value)}`} style={{ textAlign: "right" }}>{r.value == null ? "–" : unit(r.value)}</div>
          </div>
        );
      })}
    </div>
  );
}
