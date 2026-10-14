"use client";
import { useEffect, useState } from "react";

export type Basket = {
  id: string; type: "sector" | "theme" | "theme_country" | "market"; market: string; name: string;
  theme: string | null; sector: string | null; country: string | null; n: number; tickers: string[];
  as_of: string;
  ret_1d: number | null; ret_5d: number | null; ret_20d: number | null;
  ret_1d_usd: number | null; ret_5d_usd: number | null; ret_20d_usd: number | null;
  ew_ret_1d: number | null; ew_ret_5d: number | null; ew_cw_gap_5d: number | null;
  rel_1d: number | null; rel_5d: number | null; rel_20d: number | null; rel_60d: number | null;
  rel_1d_usd: number | null; rel_5d_usd: number | null; rel_20d_usd: number | null;
  beta: number | null; residual_1d: number | null; residual_5d: number | null; residual_20d: number | null; residual_5d_z: number | null;
  rs_ratio: number | null; rs_mom: number | null; quadrant: string | null; quadrant_prev: string | null; persist_days: number; transition: boolean;
  turnover_share: number | null; turnover_share_5d: number | null; turnover_share_z: number | null; turnover_share_1d_z: number | null; turnover_quadrant: string | null;
  pct_above_20: number | null; pct_above_50: number | null; pct_above_200: number | null; breadth_change_5d: number | null; breadth_change_z: number | null;
  advancers: number; decliners: number;
  flow_1d: number | null; flow_5d: number | null; flow_20d: number | null; flow_z: number | null; flow_as_of: string | null; flow_coverage: number | null;
  flow_detail: Record<string, number | null> | null;
  composite: number | null; composite_components: Record<string, number | null>;
  series: { rrg_trail: [number, number][]; rel_index_120d: number[]; turnover_share_60d: number[]; flow_20d_series: number[] | null };
  contributors: { total: number; hhi: number; n: number; top: Contrib[]; bottom: Contrib[] } | null;
};
export type Contrib = { ticker: string; name: string; ret: number; contrib: number; share_of_move: number | null };
export type Regime = {
  as_of: string; benchmark: string; bench_level: number; bench_ret_1d: number | null; bench_ret_5d: number | null; bench_ret_20d: number | null;
  bench_ret_1d_usd: number | null; bench_ret_5d_usd: number | null; fx_ret_5d: number | null; bench_ret_z: number | null; realised_vol_20d: number | null;
  dispersion: number | null; dispersion_z: number | null; avg_corr: number | null; avg_corr_pctile: number | null; label: string;
  breadth_pct_above_20: number | null; breadth_pct_above_50: number | null; advancers: number | null; decliners: number | null; ew_cw_gap_5d: number | null;
  dispersion_series_60d: number[]; avg_corr_series_60d: number[];
};
export type Latest = {
  meta: { run: string; generated_at: string; as_of: Record<string, string>; sources: any; params: any; basket_count: number; universe_counts: Record<string, number> };
  regime: Record<string, Regime>;
  baskets: Basket[];
  leaders: string[]; laggards: string[];
  transitions: { id: string; name: string; market: string; from: string; to: string }[];
  persistence_milestones: { id: string; name: string; market: string; quadrant: string; days: number }[];
  heatmap: { sectors: string[]; markets: string[]; values: Record<string, (number | null)[][]> };
  themes: { id: string; name: string; description: string; total: Basket; countries: Record<string, Basket>; leadlag: Record<string, any> | null }[];
  market_flows: Record<string, any>;
  events: { date: string | null; market: string; label: string; kind: string }[];
  scorecard: any;
  digest: { markdown: string; narrative: string | null };
};

export const MARKET_NAMES: Record<string, string> = { US: "United States", KR: "Korea", HK: "Hong Kong", JP: "Japan", TW: "Taiwan", GLOBAL: "Cross-market" };
export const MARKETS = ["US", "KR", "HK", "JP", "TW"];

let cache: Latest | null = null;
export function useLatest(): { data: Latest | null; error: string | null } {
  const [data, setData] = useState<Latest | null>(cache);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (cache) return;
    fetch("/data/latest.json", { cache: "no-store" })
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((j) => { cache = j; setData(j); })
      .catch((e) => setError(String(e)));
  }, []);
  return { data, error };
}

export const pct = (v: number | null | undefined, nd = 1) => v == null ? "–" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(nd)}%`;
export const num = (v: number | null | undefined, nd = 2) => v == null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(nd)}`;
export const fmt = (v: number | null | undefined, nd = 1) => v == null ? "–" : v.toFixed(nd);
export const sign = (v: number | null | undefined) => v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "";
export function money(v: number | null | undefined, ccy: string): string {
  if (v == null) return "–";
  const u: Record<string, [number, string]> = { KRW: [1e9, "bn"], TWD: [1e9, "bn"], HKD: [1e6, "m"], JPY: [1e9, "bn"], USD: [1e6, "m"] };
  const [d, s] = u[ccy] ?? [1e6, "m"];
  return `${v >= 0 ? "+" : ""}${(v / d).toLocaleString(undefined, { maximumFractionDigits: 1 })}${s}`;
}
export const label = (b: Basket) => b.type === "theme" ? b.name : b.type === "theme_country" ? b.name : `${MARKET_NAMES[b.market]} · ${b.name}`;
