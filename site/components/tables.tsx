"use client";
import Link from "next/link";
import { Basket, MARKET_NAMES, fmt, label, num, pct, sign } from "@/lib/data";
import { Sparkline } from "./charts";

export function Quadrant({ q }: { q: string | null }) {
  return q ? <span className={`pill ${q}`}>{q}</span> : <span className="note">–</span>;
}

export function BasketRow({ b, showMarket = true, usd = false }: { b: Basket; showMarket?: boolean; usd?: boolean }) {
  const top = b.contributors ? [...b.contributors.top, ...b.contributors.bottom].sort((x, y) => Math.abs(y.contrib) - Math.abs(x.contrib))[0] : undefined;
  const rel5 = usd ? b.rel_5d_usd : b.rel_5d;
  return (
    <tr>
      <td>
        {showMarket && <span className={`dot m-${b.market}`} />}
        {b.type === "sector" ? <Link href={`/markets/${b.market}/`}>{showMarket ? label(b) : b.name}</Link> : <Link href="/themes/">{b.name}</Link>}
        <span className="note"> {b.n}</span>
      </td>
      <td className={`num ${sign(b.composite)}`}><b>{num(b.composite, 1)}</b></td>
      <td className={`num ${sign(rel5)}`}>{pct(rel5)}</td>
      <td className={`num ${sign(b.residual_5d)}`}>{pct(b.residual_5d)} <span className="note">({num(b.residual_5d_z, 1)})</span></td>
      <td className={`num ${sign(b.turnover_share_z)}`}>{num(b.turnover_share_z, 1)} <span className="note">{b.turnover_quadrant ?? ""}</span></td>
      <td className={`num ${sign(b.flow_z)}`}>{b.flow_z == null ? <span className="note">–</span> : num(b.flow_z, 1)}</td>
      <td className="num">{fmt(b.pct_above_20, 0)}% <span className={`note ${sign(b.breadth_change_5d)}`}>{num(b.breadth_change_5d, 0)}</span></td>
      <td><Quadrant q={b.quadrant} /> <span className="note">{b.persist_days}d</span></td>
      <td><Sparkline values={b.series.rel_index_120d} base={100} /></td>
      <td className="small">{top ? <>{top.name.slice(0, 20)} <span className={sign(top.ret)}>{pct(top.ret)}</span>{top.share_of_move != null && top.share_of_move > 0 && top.share_of_move < 5 && <span className="note"> {Math.round(top.share_of_move * 100)}% of move</span>}</> : "–"}</td>
    </tr>
  );
}

export function BasketTable({ baskets, showMarket = true, usd = false, title }: { baskets: Basket[]; showMarket?: boolean; usd?: boolean; title?: string }) {
  return (
    <div className="card" style={{ overflowX: "auto" }}>
      {title && <h3>{title}</h3>}
      <table>
        <thead>
          <tr>
            <th>Basket</th><th className="num">Score</th><th className="num">Rel 5d{usd ? " USD" : ""}</th><th className="num">β-adj resid 5d (z)</th>
            <th className="num">Turnover z</th><th className="num">Flow z</th><th className="num">&gt;20DMA (Δ5d)</th><th>RRG</th><th>Rel 120d</th><th>Top contributor 1d</th>
          </tr>
        </thead>
        <tbody>{baskets.map((b) => <BasketRow key={b.id} b={b} showMarket={showMarket} usd={usd} />)}</tbody>
      </table>
    </div>
  );
}

export function Contributors({ b }: { b: Basket }) {
  if (!b.contributors) return null;
  const c = b.contributors;
  const row = (x: typeof c.top[number]) => (
    <tr key={x.ticker}><td>{x.name} <span className="note">{x.ticker}</span></td><td className={`num ${sign(x.ret)}`}>{pct(x.ret)}</td><td className={`num ${sign(x.contrib)}`}>{pct(x.contrib, 2)}</td><td className="num">{x.share_of_move != null && Math.abs(x.share_of_move) < 5 ? `${Math.round(x.share_of_move * 100)}%` : "–"}</td></tr>
  );
  return (
    <table>
      <thead><tr><th>{b.name} · 1d {pct(c.total)} · concentration HHI {fmt(c.hhi, 2)}</th><th className="num">Ret</th><th className="num">Contrib</th><th className="num">Share</th></tr></thead>
      <tbody>{c.top.map(row)}{c.bottom.map(row)}</tbody>
    </table>
  );
}

export function MarketPill({ m }: { m: string }) {
  return <span><span className={`dot m-${m}`} />{MARKET_NAMES[m] ?? m}</span>;
}
