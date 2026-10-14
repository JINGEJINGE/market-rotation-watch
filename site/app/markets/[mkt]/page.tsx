import { MarketView } from "@/components/market-view";

export function generateStaticParams() {
  return ["US", "KR", "HK", "JP", "TW"].map((mkt) => ({ mkt }));
}

export default async function MarketPage({ params }: { params: Promise<{ mkt: string }> }) {
  const { mkt } = await params;
  return <MarketView mkt={mkt} />;
}
