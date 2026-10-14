# Market Rotation Watch

Daily monitor of capital rotation — sector to sector, theme to theme, market to market — across the
US, Korea, Hong Kong, Japan and Taiwan. Free data only. See `DESIGN.md` for the full design.

Two runs a day (Singapore time): **18:00** after the Asia close and **06:30** after the US close.
Each run updates prices and investor flows, recomputes every signal, writes `data/outputs/latest.json`,
archives a Markdown digest under `digests/`, pushes a Telegram summary, and the Vercel dashboard
redeploys from the commit.

```
pipeline/      Python pipeline (run.py is the entry point; config/ holds the editable registries)
data/          universe CSVs, monthly price/flow parquet partitions, outputs (committed by the bot)
digests/       one Markdown digest per run
site/          Next.js dashboard (static export) — reads site/public/data/latest.json
.github/       scheduled workflows
```

## Two ways to run it

**Subscription-only (current choice)** — two daily memos in the Claude app, no API key, no Telegram, no dashboard:
see `SCHEDULED_TASKS.md`. The pipeline runs inside Claude scheduled tasks and rebuilds from free data each time;
`bootstrap.sh` + `MANIFEST.txt` are what those sessions fetch.

**Full mode** — GitHub Actions + Telegram + Vercel dashboard, as below. Both modes share all signal code.

## Full-mode one-time setup (about 20 minutes)

1. **Create a GitHub repository** (private is fine) and push this folder to it.
2. **Telegram**: message `@BotFather`, `/newbot`, copy the token. Start a chat with your new bot and
   send it any message. Then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the
   `chat.id` number.
3. **Anthropic API key** for the narrative: console.anthropic.com → API keys.
4. **GitHub secrets** (repo → Settings → Secrets and variables → Actions):
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ANTHROPIC_API_KEY`.
   Optional: `KRX_ID`, `KRX_PW` (a free data.krx.co.kr account) — reserved for Korean short-sale data in a later phase.
5. **Allow the bot to push**: repo → Settings → Actions → General → Workflow permissions →
   "Read and write permissions".
6. **Vercel**: import the repo, set *Root Directory* to `site`, framework Next.js, defaults otherwise.
   Every commit by the workflows redeploys the dashboard.
7. Run the **Asia-close run** workflow once by hand (Actions tab → Run workflow) to confirm Telegram arrives.

## Running locally

```
cd pipeline
pip install -r requirements.txt
python run.py --universe              # rebuild constituent lists (monthly; slow — Yahoo metadata)
python run.py --backfill              # 3-year price history (first time only)
python run.py --run asia --no-telegram --no-llm
python run.py --run asia --no-fetch   # recompute signals from stored data, no network
cd ../site && npm install && npm run dev
```

Environment variables `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ANTHROPIC_API_KEY` enable the push and
the narrative locally too. `MRW_LLM_MODEL` overrides the model (default `claude-sonnet-5-5`).

## Editing the registries

- `pipeline/config/themes.yaml` — theme baskets. Add or remove tickers (Yahoo symbols). Unresolved
  tickers are listed in `data/outputs/universe_report.json` after the next universe refresh.
- `pipeline/config/events.yaml` — manual event calendar (central banks, rebalances, seasons).
- `pipeline/config/markets.yaml` — benchmarks, sector maps, signal parameters and composite weights.

## How the signals are built (short version)

- **Price-relative**: relative return vs the market benchmark (1/5/20/60d, local and USD);
  **beta-adjusted residual** (60-day rolling beta, lagged one day); RRG coordinates (JdK-style
  approximation: RS-Ratio = 63-day z of relative strength, RS-Momentum = 21-day z of RS-Ratio) with
  quadrant, persistence and transitions.
- **Turnover**: basket share of market dollar turnover vs its 60-day baseline (z), and the
  price × turnover quadrant (Accumulation / Thin drift / Distribution / Apathy).
- **Flows**: Korea foreign/institution/retail (Naver, per stock, valued at close), Hong Kong Southbound
  (HKEX, totals + top-10 stocks), Taiwan foreign/trust/dealer (TWSE, per stock), Japan weekly (JPX).
  `flow_z` = z of the 5-day "smart" flow (foreign+institutional, Southbound, foreign+trust).
- **Breadth**: % above 20/50/200DMA, advance–decline, equal- vs cap-weighted gap, top-3 contributors, HHI.
- **Regime**: sector dispersion z and average sector correlation percentile → Rotation day / Beta day / Mixed.
- **Lead-lag**: US theme members' session return vs next-session return of each Asian country's members (60-day β).
- **Composite** = 0.35·residual z + 0.25·turnover z + 0.25·flow z + 0.15·breadth-change z, renormalised over available components.
- **Scorecard**: forward 5/20-day residual after each signal event, last two years, backfilled from history.

## Known limits

- Yahoo rate-limits aggressively; the metadata refresh is deliberately slow (one request per second).
- TWSE and Naver endpoints are undocumented; the ingesters keep the last good data if they fail and the
  digest says which sources were stale.
- Constituents are current lists applied to history (survivorship bias in the backfilled scorecard).
- No free daily US fund-flow source; US `flow_z` is empty.
