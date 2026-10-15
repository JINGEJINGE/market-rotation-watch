// MRW dispatch relay ("the doorman").
// GET or POST /api/dispatch?run=us|asia
// Starts the matching GitHub Actions workflow on JINGEJINGE/market-rotation-watch, but only
//   - inside the run's time window (Singapore time), unless ?key= matches TEST_KEY, and
//   - if no run of that workflow was created in the last 10 minutes.
// The GitHub token lives only in the GH_TOKEN environment variable on Vercel.

const OWNER = "JINGEJINGE";
const REPO = "market-rotation-watch";
const WORKFLOWS = { us: "us-close.yml", asia: "asia-close.yml" };
// [startMinute, endMinute] of the day in Singapore time (UTC+8)
const WINDOWS = { us: [4 * 60 + 30, 9 * 60], asia: [16 * 60 + 30, 20 * 60] };
const DEDUP_MINUTES = 10;

function sgtMinutes(now) {
  const sgt = new Date(now.getTime() + 8 * 3600 * 1000);
  return sgt.getUTCHours() * 60 + sgt.getUTCMinutes();
}

async function gh(path, init = {}) {
  const r = await fetch(`https://api.github.com/repos/${OWNER}/${REPO}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${process.env.GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
      "User-Agent": "mrw-dispatch-relay",
      ...(init.headers || {}),
    },
  });
  return r;
}

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const url = new URL(req.url, "http://x");
  const run = url.searchParams.get("run");
  const key = url.searchParams.get("key");
  const now = new Date();

  if (!WORKFLOWS[run]) {
    return res.status(400).json({ ok: false, error: "run must be 'us' or 'asia'" });
  }
  if (!process.env.GH_TOKEN) {
    return res.status(500).json({ ok: false, error: "GH_TOKEN is not configured on the relay" });
  }

  const bypass = process.env.TEST_KEY && key === process.env.TEST_KEY;
  const m = sgtMinutes(now);
  const [a, b] = WINDOWS[run];
  if (!bypass && (m < a || m > b)) {
    return res.status(200).json({
      ok: true, dispatched: false, reason: "outside time window",
      run, sgt_time: `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`,
      window_sgt: `${Math.floor(a / 60)}:${String(a % 60).padStart(2, "0")}-${Math.floor(b / 60)}:${String(b % 60).padStart(2, "0")}`,
    });
  }

  // Dedup: any run of this workflow created in the last DEDUP_MINUTES, or still queued/in progress?
  let recent = null;
  try {
    const r = await gh(`/actions/workflows/${WORKFLOWS[run]}/runs?per_page=5`);
    if (r.ok) {
      const j = await r.json();
      for (const w of j.workflow_runs || []) {
        const age = (now - new Date(w.created_at)) / 60000;
        if (age < DEDUP_MINUTES || w.status === "queued" || w.status === "in_progress") {
          recent = { id: w.id, status: w.status, conclusion: w.conclusion, created_at: w.created_at, event: w.event, html_url: w.html_url };
          break;
        }
      }
    }
  } catch (e) { /* dedup is best-effort */ }
  if (recent) {
    return res.status(200).json({ ok: true, dispatched: false, reason: "a run is already recent or in progress", run, recent });
  }

  const d = await gh(`/actions/workflows/${WORKFLOWS[run]}/dispatches`, {
    method: "POST", body: JSON.stringify({ ref: "main" }),
  });
  if (d.status === 204) {
    return res.status(200).json({ ok: true, dispatched: true, run, at: now.toISOString(),
      note: "poll https://raw.githubusercontent.com/JINGEJINGE/market-rotation-watch/main/data/outputs/latest.json (meta.generated_at) — a run takes about 5 minutes" });
  }
  const body = await d.text();
  return res.status(502).json({ ok: false, dispatched: false, run, github_status: d.status, github_body: body.slice(0, 300) });
};
