# Subscription-only mode: two daily memos in the Claude app, no API, no dashboard, no Telegram

This mode runs the whole pipeline inside a **Claude scheduled task**. Each firing starts a fresh cloud session on
your subscription, fetches the code zip from Google Drive, rebuilds 18 months of prices and the flow history from the free
sources, computes every signal, and then Claude itself — not the API — writes the memo and posts it as the run's
result, with a push notification to your phone. Nothing is stored between runs except the code and the
constituent lists in the Drive zip; a run takes about 15 minutes.

What you keep from the full build: every signal layer, the 17 themes, the regime verdict, flows, lead-lag,
scorecard, the heatmap image. What you give up: the dashboard (the code stays in `site/` for later) and the
cumulative digest archive in git (memos are archived in the Claude Project instead). GitHub is not involved in this mode; `bootstrap.sh` /
`MANIFEST.txt` remain for the GitHub variant.

## How it is wired (done 14 Oct 2026)

- **Code lives in Google Drive**: folder "Market Rotation Watch" → `mrw-pipeline.zip` (124 KB: pipeline code, the
  three config files, the five constituent CSVs and the metadata cache; no price or flow data, nothing secret).
  Shared as "anyone with the link, viewer" so a scheduled session can fetch it with a plain download.
  File ID `1Io_g-5wGQTiufnJ3y8VhaOg8Zc1HFrJ-` — baked into both task prompts.
- **Two Claude scheduled tasks** (created from the Cowork session, automatic approval, push notification on):
  `MRW US close memo` — 06:30 Singapore, Tue–Sat · `MRW Asia close memo` — 18:00 Singapore, Mon–Fri.
  Each run: download zip → unzip → pip install → `python run.py --run us|asia --no-telegram --no-llm` (~13 min)
  → Claude writes the memo from `digests/<date>-us|asia.md` → memo is the run's final message (push opens it)
  → heatmap/RRG image attached → copy saved to the Claude Project as `memos/<date>-us|asia.md`.
- Nothing is written back to Drive; runs are independent.

**Updating the zip** (theme edits, event calendar, monthly constituent refresh, source fixes): rebuild
`mrw-pipeline.zip` (`zip -r mrw-pipeline.zip pipeline data/universe -x '*__pycache__*'` from the repo folder, or ask
Claude), then in Drive right-click the file → *Manage versions* → *Upload new version*. The file ID stays the same,
so the tasks never need editing. Re-sharing is not needed.

**Changing a task** (time, wording of the memo): Claude app → scheduled tasks → edit the prompt or schedule; or ask
Claude in a session (`update_trigger`). Pausing: toggle the task off; nothing else to stop.

## Task 1 — "MRW US close memo"  ·  cron `30 22 * * 1-5` (06:30 SGT Tue–Sat)

```
You are producing the Market Rotation Watch US-close memo. Do all of this without asking questions; if something
fails, say so in the memo and continue with what you have.

1. In a scratch directory run:
     curl -sSL https://raw.githubusercontent.com/OWNER/REPO/main/bootstrap.sh | bash -s OWNER/REPO
     cd mrw/pipeline && pip install -q -r requirements.txt && python run.py --run us --no-telegram --no-llm
   Expect 12–18 minutes. If a Yahoo rate-limit error aborts the run, wait 10 minutes and run the python command again once.

2. Read the newest file in mrw/digests/ (it ends in -us.md). It holds the computed tables: regime per market,
   rotation leaders and laggards with their confirmation metrics, investor flows, the theme table with lead-lag,
   RRG transitions, persistence milestones, upcoming events, and a data note if any source was stale.
   Also read mrw/data/outputs/latest.json only if you need a number the digest does not show (e.g. a specific
   theme's country breakdown, contributors, or the scorecard).

3. Write the memo for Ge, an experienced investor in Singapore reading on his phone before the Asia open.
   Use ONLY numbers that appear in the digest or latest.json; never invent a figure, flow or event.
   Structure, in this order, plain English, no preamble:
     - Headline (one line): the regime verdict for the US session and the single most important rotation.
     - The read (250–350 words): where capital rotated in and out overnight and whether each move is CONFIRMED
       (turnover share up, breadth participating, beta-adjusted residual positive) or price-only; what the
       lead-lag table implies for today's KR/JP/TW/HK open by theme; anything the scorecard says about how
       reliable today's strongest signal type has been.
     - Rotating in / Rotating out: five baskets each, one line per basket: name · composite score · residual 5d ·
       turnover quadrant · RRG quadrant and days · top contributor and share of move.
     - Themes: the five biggest movers (USD), one line each with the implied Asia move where available.
     - Flows: Korea foreign/institutional, Southbound, Taiwan foreign — 1d and 5d with z-scores; Japan weekly.
     - Watch: RRG transitions and persistence milestones; events in the next two sessions.
     - Data note: as-of dates per market and any stale source.

4. Deliver it: post the complete memo as your final message (it is what the push notification opens), send
   mrw/data/outputs/charts/heatmap.png with SendUserFile so it appears under the memo, and save a copy of the memo
   to the project with project_write at path memos/<as-of date>-us.md.
```

## Task 2 — "MRW Asia close memo"  ·  cron `0 10 * * 1-5` (18:00 SGT Mon–Fri)

Identical to Task 1 with these substitutions: `--run asia`; read the newest `-asia.md`; the reader is preparing for
the US open, so the lead-lag section becomes "did Asia follow the implied US move (realised vs implied, surprise)"
and the themes section leads with the Asian country baskets; send `rrg.png` instead of `heatmap.png`; save to
`memos/<as-of date>-asia.md`.

## Why this is the efficient path

- No servers, no API key, no third-party app: the compute is the scheduled session, the "push" is the app's own
  notification, the archive is the Project.
- Stateless by design: every run rebuilds from the free sources, so nothing can silently go stale in a database;
  the cost is ~13 minutes of fetching per run, which the session does while you are asleep or at dinner.
- The narrative is written by the Claude model your subscription already includes, from the same deterministic
  tables the API version would have used, under the same "numbers only from the tables" rule.
- The dashboard can be switched on later with the original GitHub Actions + Vercel path (README) without changing
  any of the signal code.

## Known limits of this mode

- Yahoo throttling: a run that hits `Too Many Requests` retries with back-off; a second failure means that memo is
  skipped and the next run is unaffected.
- TWSE's WAF refuses roughly half of the historical requests, so Taiwan sector flow z-scores need ~30 successful
  days and may show as "–" for the first weeks. Korea, Hong Kong and Japan flows are complete from the first run.
- The scorecard is recomputed from 18 months of history each run (no live accumulation); it is still the honest
  baseline for weighting the signals.
