# MRW dispatch relay ("the doorman")

A two-function Vercel project that starts the Market Rotation Watch GitHub Actions workflows on request,
so the Claude memo tasks do not depend on GitHub's (often hours-late) cron scheduler.

- `GET /api/dispatch?run=us` or `?run=asia` — starts the workflow, but only inside the run's time window
  (US 04:30–09:00, Asia 16:30–20:00 Singapore) and only if no run was created in the last 10 minutes.
- `GET /api/status` — latest workflow runs and the newest committed digests (read-only).

The GitHub token lives only in the Vercel environment variable `GH_TOKEN` (fine-grained, this repo only,
permission Actions: read and write). No secret is needed to call the endpoints.

## Deploy (Vercel dashboard, ~3 minutes)

1. Vercel → Add New → Project → Import `JINGEJINGE/market-rotation-watch`.
2. Project name `mrw-dispatch-relay`, **Root Directory: `relay`**, Framework: Other. Deploy.
3. Settings → Environment Variables → add `GH_TOKEN` (Production) = the fine-grained GitHub token.
   Optional: `TEST_KEY` = any random string, lets `?key=<it>` bypass the time window for manual tests.
4. Settings → Deployment Protection → **Vercel Authentication: Disabled** (otherwise callers get a login page).
5. Redeploy once so the env vars are picked up, then open `https://<project>.vercel.app/api/status`.
