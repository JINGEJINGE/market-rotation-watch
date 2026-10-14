"use client";
import { useLatest } from "@/lib/data";

export function Stamp() {
  const { data } = useLatest();
  if (!data) return <span className="stamp" />;
  const asof = Object.entries(data.meta.as_of).map(([m, d]) => `${m} ${d.slice(5)}`).join(" · ");
  return <span className="stamp">{data.meta.run === "asia" ? "Asia-close run" : "US-close run"} · {asof}</span>;
}
