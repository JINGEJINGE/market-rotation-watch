# Hybrid mode: GitHub Actions computes, Claude scheduled tasks write the memos

Two daily memos arrive in the Claude app with no API key, no Telegram and no dashboard. Since 14 Oct 2026 the
work is split in two:

| Step | Where | What |
|---|---|---|
| Compute | **GitHub Actions** in the public repo `JINGEJINGE/market-rotation-watch` | `run.py --run us|asia --no-telegram --no-llm`: incremental price + flow fetch, every signal, the digest tables, `latest.json`, the PNGs. Commits the results to `main`. ~4–5 min. |
| Memo | **Claude scheduled task** (subscription, automatic approval, push notification) | Downloads `digests/<date>-*.md`, `latest.json` and the PNG from the repo with `curl` (data files only — no code is executed), writes the memo, posts it as the run's result, saves a copy to the Project under `memos/`. ~2 min. |

Why this split: the scheduled session's guardrail refuses to execute code it downloaded during the run, and it may
refuse the Project-docs rebuild too; reading a Markdown/JSON/PNG file is never gated. GitHub also gives the pipeline
persistent state (the parquet history is committed, so each run fetches a week, not 18 months; Taiwan/Korea flow
history accumulates), version control for the code, and 90 days of per-step logs.

## Schedule (Singapore time)

| | GitHub Actions workflow | Claude task | Buffer |
|---|---|---|---|
| US close | `us-close.yml` · cron `37 21 * * 1-5` UTC = **05:37 Tue–Sat** | **MRW US close memo** · `CRON_TZ=Asia/Singapore 30 6 * * 2-6` | 53 min |
| Asia close | `asia-close.yml` · cron `17 9 * * 1-5` UTC = **17:17 Mon–Fri** | **MRW Asia close memo** · `CRON_TZ=Asia/Singapore 0 18 * * 1-5` | 43 min |
| Universe refresh | `refresh-universe.yml` · 1st of month 10:00 | — | |

GitHub's cron is best-effort (5–30 min late at busy hours), hence the buffers. The Claude task checks freshness twice
(digest date, then `meta.generated_at` and `meta.run` in `latest.json`), waits 10 minutes and retries once, and only
then falls back to rebuilding the pipeline in-session from the Project docs (the previous all-in-Claude design, kept
verbatim as STEP 1-FALLBACK in both prompts).

## What the Claude task does (both prompts have the same shape)

```
STEP 1   curl digests.json → newest <date>-us|asia.md → freshness check → curl the digest, latest.json, heatmap|rrg.png
         second check: latest.json meta.run == us|asia and generated_at after 05:00 | 17:00 SGT today
STEP 1-FALLBACK (only if STEP 1 fails twice)  rebuild from the 23 Project docs and run the pipeline in-session (12–18 min)
STEP 2   read the digest; latest.json only for numbers the digest lacks
STEP 3   memo: headline · the read (250–350 words) · rotating in/out (5 each) · themes · flows · watch · data note
STEP 4   memo as final message (push opens it) · SendUserFile heatmap.png | rrg.png · project_write memos/<date>-us|asia.md
```

The live prompts are on the tasks themselves (Claude app → scheduled tasks). A disabled one-shot task
**MRW hybrid test (US)** keeps the test variant (saves to `memos/<date>-us-hybridtest.md`); enable and run it to re-test.

## Where things live

- **Code and data of record: the GitHub repo.** `pipeline/`, `pipeline/config/*.yaml`, `data/universe/*.csv`,
  `data/prices/**` and `data/flows/**` (parquet, committed by the bot), `data/outputs/`, `digests/`, `site/`.
  The working copy on the Mac is `Market Rotation Watch/market-rotation-watch/` (not a git checkout — see "Updating").
- **Project docs (23 files):** a copy of the pipeline source and constituent CSVs, used only by STEP 1-FALLBACK.
  Keep them in sync with the repo when the code changes (`project_write` with `local_path`).
- **Memos:** `memos/<date>-us.md` and `memos/<date>-asia.md` in the Project. Digest tables: `digests/` in the repo.

## Updating the code (theme edits, event calendar, source fixes)

1. Edit the file in the Mac folder `market-rotation-watch/`.
2. Push to GitHub. From a Cowork session the push is done from the Mac's VM (the cloud workspace's git proxy only
   pushes to pre-authorised repos): the VM keeps a clone in `$HOME/mrw-repo/market-rotation-watch` with the token in
   `$HOME/.mrw/gh_token`; copy the changed file in, commit, `git pull --rebase`, push. Or push from Terminal with your
   own GitHub login once the Mac folder is a clone.
3. Overwrite the matching Project doc(s) so the fallback matches.
4. A new source file also needs its path added to the F2 list in both task prompts.

Constituent refresh runs monthly on Actions by itself (`refresh-universe.yml`); after it, copy the five
`data/universe/*.csv` and `meta_cache.csv` into the Project docs if you want the fallback to use the new lists.

## Operating notes

- Manual run: repo → Actions → workflow → Run workflow (or `POST /repos/.../actions/workflows/<file>/dispatches`).
  Do not run the Asia workflow while Asia is open: it commits an intraday snapshot stamped with today's date (the
  17:17 run overwrites it, and the Claude task's `generated_at` check ignores it).
- Logs: Actions → the run → "Run pipeline" step. Look for `ERROR mrw` / `WARNING mrw` lines, the per-market
  `N/N tickers, last date` lines and `run us|asia complete in Ns`.
- `prices.py` isolates each market: a bad batch or a delisted new constituent no longer aborts the whole update,
  and the digest's data note says which market was not updated. Delisted symbols in `themes.yaml` still cost a
  60-second wait each run — remove them (14 Oct: `0877.HK`, `7342.T`).
- Southbound "failed: '-'" warnings on mainland holidays (e.g. Golden Week) are expected: no Southbound trading.
- Both workflows share the concurrency group `mrw-pipeline`; the commit step rebases with `-X theirs` so a run's
  own outputs always win if another run committed meanwhile.
- Free-tier Actions budget: ~5 min × ~43 runs/month ≈ 220 min, against 2,000 (public repos are unlimited anyway).
- Pausing: toggle the Claude task off; the Actions workflow can keep running (cheap) or be disabled in the Actions tab.

## Known limits

- Yahoo throttling: the runner's IP is a GitHub datacenter range; a `Too Many Requests` abort is retried with back-off
  and the digest reports the stale market. If it recurs, move the cron a few minutes or add a second attempt.
- TWSE's WAF refuses roughly half of the historical requests; with committed history this now heals over time.
- Constituents are current lists applied to history (survivorship bias in the backfilled scorecard).
- No free daily US fund-flow source; US `flow_z` is empty.
