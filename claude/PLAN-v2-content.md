# Market Rotation Watch — PLAN v2 content (excerpt: §5–7)

*Excerpt committed from the Claude Project's `claude/PLAN-v2-content.md` on 14 Oct 2026 (sections 5–7, verbatim).
§1–4 (the memo structure) live in the Project copy.*

## 5. Signal and content upgrades, in priority order

**A. This week (no new data sources)**
- Move today's in-session yfinance pulls (indices, rates, FX, commodities, sector/industry ETFs, Mag 7, ADRs, country ETFs) into the pipeline as a `us_overview` block in `latest.json`, so the scheduled task downloads and renders rather than fetching. Same for an `asia_overview` block.
- Concentration and minimum-size filters on the leaders/laggards lists (n ≥ 5, |top share| ≤ 60%); flag rather than drop.
- Scorecard-weighted language in the narrative prompt: cite hit rate and n for the signal type being used; call sub-50% signals "unconfirmed".
- Thesis tracker: `data/outputs/theses.json` with up to five named rotations, each with start date, direction, confirming metrics and daily status; the task updates it and prints it in the Watch section.
- Fix the Taiwan flow metadata inconsistency (fetch log says 2026-07-31, table says 2026-10-13) and surface HK Southbound top-10-only coverage in the data note automatically.
- Events file: populate from the project calendar (FOMC 28 Oct, BOJ 30 Oct, BOK 22 Oct, MSCI 11 Nov / 1 Dec, HSTECH 7 Dec) and add the S&P 500 earnings calendar from yfinance so "who reports in the next two sessions" is automatic — Q3 bank earnings start this week and the memo said "nothing scheduled".
- Asia memo rebuilt on the §4 structure with the same template.

**B. Next two weeks (free data, more insight)**
- Factor lens from ETF pairs: growth/value (IWF/IWD), momentum (MTUM), low-vol vs high-beta (SPLV/SPHB), small/large (IWM/SPY), equal/cap (RSP/SPY), cyclicals/defensives (XLI+XLY+XLF vs XLP+XLU+XLV). Five numbers that put the sector rotation in IC vocabulary.
- Rates and credit context: 2s10s, real yields (TIP vs IEF), HYG/LQD spread proxy, VIX term structure (VIX vs VIX3M) — all yfinance.
- US positioning proxies: sector-ETF volume anomalies (already in the design, not yet in the memo), CBOE put/call, weekly CFTC COT for S&P and Nasdaq futures.
- Theme membership refresh: add Nasdaq-100 names to the US sector universe so SPCX, CBRS, SKHY and the 2026 listings sit in sectors, not only themes.

**C. Later**
- Intraday-to-close behaviour (open-to-close vs close-to-close) to separate overnight gaps from cash-session flows; this is where "did Asia follow" becomes measurable at the open.
- Chinese client-note variant; A-shares / Northbound; paid ETF-flow feed if the US flow proxy proves too weak.

## 6. Decisions (Ge, 14 Oct)

1. Keep the one-line read-across to the Asia open in the US memo.
2. Delivery: PDF attached to the push plus a three-line summary in the chat.
3. US sector universe: S&P 500 ∪ Nasdaq-100.
4. ADR and Asia single-name lists as proposed.
5. Thesis tracker seeded by the pipeline from the composite, not by hand.
6. "The read" is written as insight blocks — a one-line claim, two to four evidence lines, one "so what" — not prose paragraphs.

## 7. Status and what gates the rest

Done on 14 Oct, in-session: the US template kit (`claude/memo_template/`), the restructured read, the US-close PDF for
13 Oct, and the **MRW US close memo** task prompt replaced so tomorrow's 06:30 run produces the v2 PDF plus the
three-line summary. None of this needed a code change in the repo: the overview data is fetched from Yahoo inside the
task and the pipeline's `latest.json` is used as is.

What is not done is gated by one thing — a push to the GitHub repo, which this cloud session cannot do (the token lives
on the Mac's VM; see `SCHEDULED_TASKS.md` → "Updating the code"). Everything in the list below is a few hours of work in a
session linked to the Mac, not weeks; the phasing in §5 was pacing, not a constraint:

- S&P 500 ∪ Nasdaq-100 universe (`universe/build.py`, `markets.yaml`) — repo push, then one `refresh-universe` run.
- Concentration / minimum-size filters on the leaders lists and the scorecard-weighted wording (`signals/build.py`,
  `digest/build.py`) — repo push.
- Thesis tracker (`data/outputs/theses.json`, seeded from composite crossings and RRG transitions, carried day to day) —
  repo push; the memo kit then prints it in the Watch section.
- Events: populate `events.yaml` from the project calendar and add the earnings calendar — repo push.
- `us_overview` / `asia_overview` blocks in `latest.json` so the task stops fetching Yahoo itself — repo push.
- Asia memo on the same kit (`asia_close.html`, `fetch_asia_overview.py`) — can be built in-session like the US one;
  it needs no repo change, only the Asia task prompt replaced. Next item.

The only item that takes weeks by nature is the scorecard for any **new** signal (factor lens, positioning proxies):
hit rates need live history to accumulate before the memo can quote them, though the backfill from price history
gives a first estimate on day one as it did for the existing signals.
