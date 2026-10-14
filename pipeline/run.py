"""Market Rotation Watch — pipeline entry point.

  python run.py --run asia            # evening run (after Asia close)
  python run.py --run us              # morning run (after US close)
  python run.py --run asia --no-fetch # recompute from stored data only
  python run.py --universe            # rebuild constituent lists + metadata (monthly)
  python run.py --backfill            # full 3-year price backfill
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mrw.config import DIGEST_DIR, HISTORY_DIR, OUTPUT_DIR, SITE_DATA_DIR, log, write_json  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", choices=["asia", "us"], default=None)
    ap.add_argument("--universe", action="store_true", help="rebuild universes and metadata")
    ap.add_argument("--backfill", action="store_true", help="full price backfill")
    ap.add_argument("--no-fetch", action="store_true", help="skip all network fetches")
    ap.add_argument("--no-flows", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    sources: dict = {}

    if args.universe:
        from mrw.universe.build import build_all
        sources["universe"] = build_all()

    if args.backfill:
        from mrw.ingest.prices import update_prices
        sources["prices"] = update_prices(full=True)

    if not args.run:
        log.info("done in %.0fs", time.time() - t0)
        return 0

    if not args.no_fetch:
        from mrw.ingest.prices import update_prices
        try:
            sources["prices"] = update_prices(full=False)
        except Exception as e:  # noqa: BLE001
            log.error("price update failed: %s", e)
            sources["prices"] = {"error": repr(e)[:200]}
        if not args.no_flows:
            from mrw.ingest.flows import update_all
            sources["flows"] = update_all()

    from mrw.signals.build import build_outputs
    out = build_outputs(args.run, sources)

    from mrw.digest.build import digest_markdown, telegram_text
    md = digest_markdown(out, args.run)
    narrative = None
    if not args.no_llm:
        from mrw.digest.narrative import write_narrative
        narrative = write_narrative(md, args.run)
    if narrative:
        md = md.replace("## 1. Regime", f"## 0. Read\n\n{narrative}\n\n## 1. Regime", 1)
    out["digest"] = {"markdown": md, "narrative": narrative}

    stamp = max(out["meta"]["as_of"].values())
    write_json(OUTPUT_DIR / "latest.json", out)
    write_json(HISTORY_DIR / f"{stamp}-{args.run}.json", {k: v for k, v in out.items() if k != "baskets"} | {
        "baskets": [{k: v for k, v in b.items() if k not in ("series", "tickers")} for b in out["baskets"]]})
    (DIGEST_DIR / f"{stamp}-{args.run}.md").write_text(md, encoding="utf-8")
    # dashboard copies
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(OUTPUT_DIR / "latest.json", SITE_DATA_DIR / "latest.json")
    digests = sorted(p.name for p in DIGEST_DIR.glob("*.md"))
    write_json(SITE_DATA_DIR / "digests.json", {"files": digests[::-1]})
    (SITE_DATA_DIR / "digests").mkdir(exist_ok=True)
    for p in DIGEST_DIR.glob("*.md"):
        shutil.copy(p, SITE_DATA_DIR / "digests" / p.name)

    from mrw.digest.charts import heatmap_png, rrg_png
    chart_dir = OUTPUT_DIR / "charts"
    chart_dir.mkdir(exist_ok=True)
    try:
        heat = heatmap_png(out, chart_dir / "heatmap.png")
        rrg = rrg_png(out, chart_dir / "rrg.png", types=("sector",), markets=("KR", "HK", "JP", "TW") if args.run == "asia" else None)
        shutil.copy(heat, SITE_DATA_DIR / "heatmap.png")
        shutil.copy(rrg, SITE_DATA_DIR / "rrg.png")
    except Exception as e:  # noqa: BLE001
        log.warning("charts failed: %s", e)
        heat = rrg = None

    if not args.no_telegram:
        from mrw.digest.telegram import send_photo, send_text
        send_text(telegram_text(out, args.run, narrative))
        if args.run == "us" and heat:
            send_photo(heat, "Cross-market heatmap: beta-adjusted 5d relative return (z)")
        elif rrg:
            send_photo(rrg, "Relative rotation, Asia sectors")

    log.info("run %s complete in %.0fs — as of %s", args.run, time.time() - t0, out["meta"]["as_of"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
