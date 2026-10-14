# Market Rotation Watch — Design

*Version 0.1 — 13 Oct 2026. Owner: Ge Jin. Status: approved and built (Phase 1 + 2); see §11 for build notes.*

## 1. Purpose

A personal research system that answers, twice a day, one question: **where is capital rotating to and from — across sectors, across themes, and across the US, Korea, Hong Kong, Japan and Taiwan markets — and is the move real?**

"Real" means it is confirmed by more than price: turnover is following, identifiable investors are buying, breadth inside the group is participating, and the move survives after stripping out the market's own direction.

Audience: Ge, as an input to his own market view and positioning. English throughout. A client-facing Chinese note is a later extension, not a v1 requirement.

## 2. Decisions taken (from the 13 Oct scoping session)

| Decision | Choice |
|---|---|
| Markets | US, Korea, Hong Kong, Japan, **plus Taiwan** (closes the AI supply-chain gap). China A-shares deferred. |
| Signal layers (v1) | Price-relative (RRG-style, beta-adjusted) · Turnover share · Investor-type flows (Asia) · Breadth & concentration |
| Themes | ~12 cross-market baskets seeded by Claude, held in an editable registry file |
| Runs | Two per day, Singapore time: **Asia-close run** (evening) and **US-close run** (~06:30) |
| Compute | GitHub Actions cron (Python pipeline) → results committed to repo → Next.js dashboard on Vercel |
| Data | Free sources only (see §5) |
| Delivery | Vercel dashboard + Telegram push + dated Markdown archive of every digest in the repo |
| Narrative | LLM-written (Claude API) on top of deterministic tables; the LLM may only cite numbers present in the tables |
| Currency | USD primary for cross-market comparison, local currency shown alongside |

## 3. What "rotation" means in this system

Each **basket** (a sector within a market, or a cross-market theme) gets the same set of measurements. Rotation is a *change in relative position*, so every metric is computed against a baseline and reported as a z-score where history allows.

### 3.1 Price-relative layer
- Relative return vs the market benchmark at 1d / 5d / 20d / 60d, in local and USD terms.
- **Beta-adjusted residual return**: basket return minus (rolling 60-day beta × benchmark return). This is the headline price signal — it prevents defensives from "leading" on every down day.
- **RRG coordinates**: RS-Ratio (smoothed relative strength, centred on 100) and RS-Momentum (rate of change of RS-Ratio). Quadrant = Leading / Weakening / Lagging / Improving. The system records quadrant *transitions* and **days of persistence** in the current quadrant.
- Equal-weighted and cap-weighted versions of every return; the gap between them is itself reported (large gap = move driven by a few mega-caps).

### 3.2 Turnover layer
- Basket share of total market dollar turnover (universe total), vs its own 20d and 60d mean, as a z-score.
- **Price × turnover quadrant** for each basket: price up + share up = *accumulation*; price up + share down = *thin drift / short covering*; price down + share up = *distribution*; price down + share down = *apathy*.

### 3.3 Investor-type flow layer (Asia only in v1)
- **Korea**: daily foreign / institutional / individual net buying per stock (Naver), valued at close, aggregated to sector and theme; 1d / 5d / 20d and z-score vs 1y.
- **Hong Kong**: daily Southbound (Stock Connect) net buying — market total plus top-10 stock contributions mapped to sectors.
- **Taiwan**: daily foreign / investment-trust / dealer net buying per stock (TWSE), aggregated to sector and theme.
- **Japan**: weekly investor-type net buying (JPX), market level, one-week lag — shown as context, not as a daily signal.
- **US**: no free daily flow source. v1 uses sector-ETF volume anomalies as a weak proxy and labels it as such. ETF creation/redemption data is a paid add-on for later.

### 3.4 Breadth & concentration layer
- % of basket constituents above their 20 / 50 / 200-day moving averages; advance–decline within the basket.
- Top-3 contributors to each basket's move and a concentration index (HHI of contributions). "Tech +2%" with 70% of it from one stock is reported as such.

### 3.5 Regime context (market level)
- Benchmark return, 20d realised vol, **cross-sector dispersion** (std of sector returns) and **average pairwise correlation** of sector returns. High dispersion + low correlation = a rotation day; low dispersion + high correlation = a beta day. The digest opens with this line so rotation signals are read in context.

### 3.6 Cross-market lead-lag
- For each theme, the US-session return of its US members vs the next Asia-session return of its KR / JP / TW / HK members. Rolling 60-day transmission coefficient and today's realised transmission vs typical. This is the morning digest's "what the overnight US move implies for the Asia open" and the evening digest's "did Asia follow?"

### 3.7 Composite rotation score
- Per basket: weighted sum of z-scores — beta-adjusted 5d relative return, turnover-share z, flow z (where available), breadth change. Weights live in config; every component is displayed next to the score so it stays auditable.

### 3.8 Signal scorecard
- Every "entered Leading quadrant" and "composite score crossed threshold" event is logged with its forward 5d and 20d relative return. Because all signals are computable from history, the scorecard is backfilled from the 3-year history on day one and accumulates from there. This is what tells Ge which signals deserve weight.

### 3.9 Event overlay
- Exchange holidays from the `exchange_calendars` library (NYSE, KRX, HKEX, TSE, TWSE) — trading-day alignment across five calendars is handled here.
- Manual events file: index rebalances (MSCI, KOSPI 200, Nikkei 225, HSI), FOMC / BOJ / BOK / CBC meetings, earnings-season windows, option expiries. Shown in the digest for today and the next two sessions.

## 4. Universe

| Market | Universe | Benchmark | Sector scheme | Source |
|---|---|---|---|---|
| US | S&P 500 | S&P 500 (SPY) | GICS 11 | Wikipedia |
| Korea | KOSPI 200 | KOSPI | Yahoo sector → harmonised 11 | Naver API |
| Hong Kong | HSI ∪ HSTECH ∪ HSCEI (~100) | HSI | Yahoo sector → harmonised 11 | Wikipedia |
| Japan | TOPIX 500 (Core30 + Large70 + Mid400) | TOPIX (via 1306.T ETF; Nikkei 225 shown for reference only) | JPX-17 → harmonised 11 | JPX listed-companies file |
| Taiwan | Top 150 by market cap on TWSE main board | TAIEX | Yahoo sector → harmonised 11 | TWSE daily file + Yahoo |

Constituents and sector tags are refreshed monthly and committed as CSVs, so every run is reproducible. Historical membership is not tracked in v1 (mild survivorship bias in the backfilled scorecard — noted, acceptable for a research tool).

Theme baskets are defined in `config/themes.yaml` and may include tickers outside the sector universes (e.g. KOSDAQ names). Every ticker is validated against yfinance on load; unresolved tickers are reported, never silently dropped. Seed list (to be edited by Ge):

v2 (after Ge's review, 13 Oct): 1. AI Compute & HBM  2. AI Optics & Interconnect  3. Memory Cycle  4. Semicap Equipment  5. AI Power & Nuclear  6. Defense  7. Space Economy (SpaceX is private — listed proxies until an IPO)  8. Robotics & Automation  9. Shipbuilding & Shipping  10. Precious & Critical Metals  11. Fintech & Trading Platforms (exchanges, brokers, payments)  12. Crypto-linked Equities  13. Biotech & GLP-1  14. China AI & Semis. Dropped: K-Culture & Beauty, Japan Rate Normalisation, China Consumer & Platforms.

## 5. Data sources (all free; verified 13 Oct 2026 from a cloud IP)

| Need | Source | Status | Risk / mitigation |
|---|---|---|---|
| Daily OHLCV, all markets; FX | yfinance | ✅ | Pin version; chunked downloads with retry; Stooq as fallback for prices |
| S&P 500 list + GICS | Wikipedia | ✅ | Validate row count each refresh |
| KOSPI 200 list | Naver mobile API | ✅ | Undocumented API — validate count, keep last good copy |
| KR investor flows (per stock, daily) | Naver mobile API | ✅ | Same |
| KR short-sale volume | KRX data portal | ⚠️ needs free login | Optional; `KRX_ID` / `KRX_PW` secrets enable it |
| HSI / HSTECH / HSCEI lists | Wikipedia | ✅ | hsi.com.hk blocked from cloud |
| HK Southbound daily | HKEX daily-stat JS file | ✅ | Published after close; evening run timed accordingly |
| JP listed companies + sectors + TOPIX size | JPX xlsx | ✅ | Monthly file |
| JP investor-type weekly | JPX xlsx | ✅ | One-week lag, context only |
| TW all-stock daily quotes; TW institutional flows | TWSE JSON | ✅ | WAF-sensitive: pace requests, retry, fall back to last good |
| Sector tags for KR / HK / TW | Yahoo per-ticker info | ✅ | Slow — cached monthly |
| Holidays | exchange_calendars | ✅ | — |

Known gap: no daily US fund-flow source for free. Accepted for v1.

Fallback if GitHub's IP range is blocked by TWSE or Naver: the same pipeline runs unchanged on Ge's Mac under launchd and pushes to the repo.

## 6. Architecture

```
GitHub repo: market-rotation-watch
├── pipeline/            Python 3.12
│   ├── config/          universe.yaml · themes.yaml · events.yaml · weights.yaml
│   ├── universe/        constituent builders per market (monthly)
│   ├── ingest/          prices (yfinance) · flows_kr · flows_hk · flows_tw · flows_jp · fx
│   ├── signals/         relative · rrg · turnover · breadth · flows · regime · leadlag · composite · scorecard
│   ├── digest/          tables → markdown → LLM narrative → telegram
│   └── run.py           entry: --run asia | us
├── data/
│   ├── universe/        committed CSVs (refreshed monthly)
│   ├── prices/{mkt}/{YYYY-MM}.parquet   monthly partitions → tiny daily diffs
│   ├── flows/{mkt}/{YYYY-MM}.parquet
│   └── outputs/         latest.json + history/{date}-{run}.json
├── digests/             YYYY-MM-DD-asia.md · YYYY-MM-DD-us.md
├── site/                Next.js (static), reads data/outputs → Vercel
└── .github/workflows/   asia-close.yml · us-close.yml · refresh-universe.yml
```

Storage is the repo itself. Monthly parquet partitions mean each daily run rewrites only the current month's file (~200 KB per market), so the repo stays small for years. No database to operate.

Schedule (UTC in cron; SGT shown):
- **Asia-close run**: 10:00 UTC = 18:00 SGT. *Proposed 18:00 rather than 17:30* so HKEX's Southbound file and TWSE's institutional file (both published 16:00–17:30 SGT) are reliably present. Easy to move earlier once we see actual publication times.
- **US-close run**: 22:30 UTC = 06:30 SGT.
- **Universe refresh**: first Saturday of each month.

Secrets in GitHub: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ANTHROPIC_API_KEY`; optional `KRX_ID`, `KRX_PW`.

## 7. The digest

Both runs produce the same skeleton with different emphasis.

1. **Regime line** — one sentence per market: benchmark move, dispersion, correlation → "rotation day" or "beta day".
2. **Top movers** — the five baskets with the highest and lowest composite rotation score, with components shown.
3. **Confirmation table** — for each top mover: beta-adj return · turnover-share z · flow z · breadth change · top-3 contributors and their share of the move.
4. **Flows** — KR by investor type, HK Southbound, TW institutional; 1d and 5d.
5. **Themes cross-market** — each theme's return by member country, USD; lead-lag read (morning: implied for Asia open; evening: did Asia follow).
6. **Watch list** — RRG quadrant transitions today; baskets at persistence milestones (5th / 10th / 20th day leading or lagging).
7. **Events** — holidays, rebalances, central-bank meetings for the next two sessions.
8. **Narrative** — ~300 words from Claude, generated from sections 1–7 only, with the instruction that every number it uses must appear above. Written last; shown first in Telegram.

Telegram: narrative + top-movers table as text, plus one image (cross-market heatmap in the morning, RRG in the evening). Markdown archive: full digest committed to `digests/`.

## 8. Dashboard (Vercel)

Static Next.js site, rebuilt on every data commit.

- **Overview** — regime strip for five markets; cross-market heatmap (harmonised sector × market, beta-adj 5d relative return); composite leaders and laggards; latest digest narrative.
- **Market pages** (×5) — RRG chart with 10-day trails; price × turnover quadrant; breadth table; flows panel (where available); contributors.
- **Themes** — cross-market basket table; per-theme page with member-country breakdown and lead-lag chart.
- **Flows** — KR / HK / TW investor-type views over 20 and 60 days.
- **Scorecard** — hit rates and average forward returns per signal type, per market.
- **Digest archive**.

## 9. Phasing

- **Phase 1 (build now)**: repo skeleton; universe builders; price/FX ingestion with 3-year backfill; price-relative, turnover, breadth, regime and composite signals; template digest + LLM narrative; Telegram; Actions workflows; dashboard Overview + Market pages + Themes.
- **Phase 2**: KR / HK / TW flow ingestion and flow signals; lead-lag; scorecard with historical backfill; Flows and Scorecard pages.
- **Phase 3**: threshold alerts (only after the scorecard says which signals matter); KRX short-sale data via login; Chinese client-note variant; China A-shares / Northbound; paid US ETF-flow feed if wanted.

## 10. Risks and open questions

- **Source breakage** is the main operational risk with free data. Every ingester keeps the last good copy and the run reports which sources were stale, rather than failing the whole run.
- **Survivorship** in the backfilled scorecard (current constituents applied to history). Acceptable for v1; fixable by snapshotting constituents monthly from now on.
- **Taiwan universe** is a market-cap cut rather than an official index because the TWSE index files are not reachable from the cloud. Fine for rotation purposes.
- **Open for Ge**: (a) accept 18:00 SGT for the evening run? (b) any themes to add/remove from the seed list before build? (c) a Telegram bot token and chat ID, an Anthropic API key, and a GitHub repo name are needed before the first scheduled run — the pipeline can be built and tested without them.

## 11. Build notes (13 Oct 2026)

What was built: everything in Phases 1 and 2 — universes, 3-year price backfill, flow ingestion for KR/HK/TW/JP,
all signal layers, composite, lead-lag, scorecard, digest + LLM narrative + Telegram, GitHub Actions workflows, and
the Next.js dashboard (Overview, five market pages, Themes, Flows, Scorecard, Digest archive).

Deviations from the design, found on contact with the data:
- **Yahoo rate limits** the per-ticker metadata endpoint hard. The universe refresh is sequential (≈1 request/s) and
  takes 20–30 minutes; it runs monthly. Japanese market caps were only partly resolved on the first pass, so Japanese
  sector baskets fall back to equal weight until the next refresh completes them.
- **Yahoo occasionally omits a completed Asian session** from daily bars for a few hours. The ingester rebuilds any
  missing recent session from 1-hour bars (close = last bar, volume = sum), verified to match the daily bar exactly.
- **Naver's trend API ignores `page`**; paging works via `bizdate`. One year of per-stock flows is kept.
- **HKEX top-10 coverage**: Hong Kong sector flows only see stocks in the daily Southbound top-10; absence is treated
  as zero and the coverage count is shown.
- **TWSE WAF** returns a 307 security page for some dates (typhoon closures and random refusals); failures are skipped.
- **Hang Seng TECH** has no Wikipedia constituents table; a static seed list (reviewed monthly) is merged with HSI/HSCEI.
- **RRG math** was smoothed after the first run (5-day EMA of relative strength; momentum from the 5-day change of the
  ratio, 3-day smoothed) — the raw daily version produced erratic trails and too many quadrant flips.
- Scorecard on day one: RRG "entered Leading" events have a 52% 5-day and 56% 20-day hit rate with +1.4% average
  20-day residual over two years across all baskets — modest, but positive and the best of the four signal types.
  Composite-threshold events are ~50/50 at 5 days; weight them accordingly until live data accumulates.

Not yet done (Phase 3): threshold alerts, KRX short-sale data, the Chinese client-note variant, China A-shares, US ETF flows.

## 12. Post-cutoff web check (13 Oct 2026)

Claude's training knowledge ends around June 2026; Ge asked for a live check of anything that may have moved. Findings and the changes made:

- **SpaceX is public.** Nasdaq: SPCX, listed 12 Jun 2026 at $135 in a ~$75–86bn raise; ~$2.1tn market cap; Nasdaq-100 fast-entry, not S&P 500 eligible (2025 net loss). Added to Space Economy. Because one $2tn name would swamp any cap-weighted basket, a **30% single-name cap** (`params.max_weight`) now applies to every cap-weighted basket, which also tames NVDA, TSMC and Samsung/Hynix in theirs.
- **Other 2026 listings added**: SK hynix Nasdaq ADR (SKHY, Jul 2026) to AI Compute and Memory; Cerebras (CBRS, May 2026) to AI Compute; Fervo (FRVO) and Standard Nuclear (STDN) to AI Power; Firefly (FLY) to Space; Hong Kong's January AI wave — Z.ai (2513.HK), MiniMax (0100.HK), Biren (6082.HK), Iluvatar CoreX (9903.HK) — to China AI; Geek+ (2590.HK), WeRide (0800.HK), Pony (2026.HK) to Robotics. EchoStar (SATS) no longer resolves and was removed.
- **Still private, watch list in themes.yaml**: Anthropic (Nasdaq targeted Oct 2026, not yet priced), OpenAI (confidential S-1, Jun 2026), Kraken, Anduril, Stripe, Databricks, Revolut, Plaid.
- **Themes that emerged or hardened after the cutoff, now added**: *AI Software & Agents* (agentic-AI disruption debate; Palo Alto's "Mythos GPT", the listed Chinese model labs), *Quantum Computing* (pure plays, risk-appetite proxy), *Energy Security & Oil* (Brent above $100 on the unresolved US–Iran conflict; energy-importer stress in Asia). Themes count is now 17.
- **Macro backdrop worth knowing for reading the signals**: the Fed, ECB, BoJ and RBA each hiked 25 bp in September 2026 (the Fed's first hike since 2023); the US 10-year is ~5.3%; September leadership narrowed to AI tech while the equal-weight S&P fell 4.8% — exactly the EW–CW gap the regime strip reports. KOSPI peaked at 9,114 on 22 Jun 2026 and is ~25% lower; foreigners were net sellers May–September with ~80% of the selling in Samsung and Hynix — the Korea flow layer is the right instrument for that.
- **Calendar corrections**: FOMC 28 Oct and 9 Dec (not 16 Dec); BOJ 30 Oct and 18 Dec; BOK 22 Oct and 26 Nov (not 15 Oct); MSCI announcement 11 Nov, effective 1 Dec; Hang Seng TECH expands from 30 to 50 constituents on 7 Dec (results 20 Nov) — the static HSTECH seed list must be refreshed then.
- **Model ID** for the narrative updated to `claude-sonnet-5-5` (the current mid-tier model; `claude-sonnet-4-5` is no longer the default).
- Not affected: data sources (all verified live), the signal mathematics, the schedule, and the dashboard.

## 13. Delivery change (14 Oct 2026)

Ge decided to defer the dashboard and run subscription-only: two daily memos (US close, Asia close) delivered inside
the Claude mobile app by Claude scheduled tasks, with no API key and no third-party channel. The pipeline was made
stateless for this — each run fetches the code and constituent lists from GitHub (`bootstrap.sh`), rebuilds 18
months of prices and the flow history from the free sources (verified: 13.5 minutes end to end from a 464 KB
folder), computes every signal, and the session's own Claude writes the memo from the digest tables. Memos are
archived in the Claude Project. Details and the two task prompts: `SCHEDULED_TASKS.md`. The Actions/Telegram/Vercel
path remains in the repo and can be switched on later without changing signal code.
