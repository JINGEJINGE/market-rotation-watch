import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { Stamp } from "@/components/stamp";

export const metadata: Metadata = {
  title: "Market Rotation Watch",
  description: "Daily sector and theme rotation monitor across US, Korea, Hong Kong, Japan and Taiwan.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="top">
          <Link className="brand" href="/">Market Rotation Watch</Link>
          <Link href="/">Overview</Link>
          <Link href="/markets/US/">US</Link>
          <Link href="/markets/KR/">Korea</Link>
          <Link href="/markets/HK/">Hong Kong</Link>
          <Link href="/markets/JP/">Japan</Link>
          <Link href="/markets/TW/">Taiwan</Link>
          <Link href="/themes/">Themes</Link>
          <Link href="/flows/">Flows</Link>
          <Link href="/scorecard/">Scorecard</Link>
          <Link href="/digests/">Digests</Link>
          <Stamp />
        </nav>
        <main>{children}</main>
        <main><div className="footer">Free-data research tool. Prices via Yahoo Finance; flows via Naver, HKEX, TWSE, JPX. Beta-adjusted residuals use a rolling 60-day beta; RRG coordinates are a JdK-style approximation (1 unit = 1σ). Not investment advice.</div></main>
      </body>
    </html>
  );
}
