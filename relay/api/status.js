// GET /api/status — latest runs of both workflows and the newest committed digests (read-only).
const OWNER = "JINGEJINGE";
const REPO = "market-rotation-watch";

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const out = { now: new Date().toISOString() };
  try {
    const r = await fetch(`https://api.github.com/repos/${OWNER}/${REPO}/actions/runs?per_page=6`, {
      headers: { Authorization: `Bearer ${process.env.GH_TOKEN}`, Accept: "application/vnd.github+json", "User-Agent": "mrw-dispatch-relay" },
    });
    const j = await r.json();
    out.runs = (j.workflow_runs || []).map(w => ({ name: w.name, event: w.event, status: w.status, conclusion: w.conclusion, created_at: w.created_at }));
  } catch (e) { out.runs_error = String(e).slice(0, 200); }
  try {
    const d = await fetch(`https://raw.githubusercontent.com/${OWNER}/${REPO}/main/site/public/data/digests.json?${Date.now()}`);
    out.digests = (await d.json()).files;
    const l = await fetch(`https://raw.githubusercontent.com/${OWNER}/${REPO}/main/data/outputs/latest.json?${Date.now()}`);
    const m = (await l.json()).meta;
    out.latest = { run: m.run, generated_at: m.generated_at, as_of: m.as_of };
  } catch (e) { out.digests_error = String(e).slice(0, 200); }
  res.status(200).json(out);
};
