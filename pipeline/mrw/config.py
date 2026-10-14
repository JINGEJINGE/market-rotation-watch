"""Configuration, paths and shared helpers."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import yaml

PIPELINE_DIR = Path(__file__).resolve().parent.parent
ROOT = PIPELINE_DIR.parent
CONFIG_DIR = PIPELINE_DIR / "config"
DATA_DIR = ROOT / "data"
UNIVERSE_DIR = DATA_DIR / "universe"
PRICES_DIR = DATA_DIR / "prices"
FLOWS_DIR = DATA_DIR / "flows"
OUTPUT_DIR = DATA_DIR / "outputs"
HISTORY_DIR = OUTPUT_DIR / "history"
DIGEST_DIR = ROOT / "digests"
SITE_DATA_DIR = ROOT / "site" / "public" / "data"

for d in (UNIVERSE_DIR, PRICES_DIR, FLOWS_DIR, OUTPUT_DIR, HISTORY_DIR, DIGEST_DIR):
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=os.environ.get("MRW_LOGLEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mrw")

DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 Safari/604.1"
)


def _load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


MARKETS_CFG = _load_yaml("markets.yaml")
MARKETS: dict = MARKETS_CFG["markets"]
PARAMS: dict = MARKETS_CFG["params"]
SECTOR_MAPS: dict = MARKETS_CFG["sector_maps"]
HARMONISED_SECTORS: list[str] = MARKETS_CFG["harmonised_sectors"]
REFERENCE_TICKERS: list[str] = MARKETS_CFG.get("reference", [])
THEMES: dict = _load_yaml("themes.yaml")["themes"]
EVENTS_CFG: dict = _load_yaml("events.yaml")

MARKET_CODES = list(MARKETS.keys())
ASIA_MARKETS = [m for m, c in MARKETS.items() if c["session"] == "asia"]


def fx_ticker(market: str) -> str | None:
    return MARKETS[market].get("fx")


def benchmark_ticker(market: str) -> str:
    return MARKETS[market]["benchmark"]


def harmonise_sector(scheme: str, local: str | None) -> str | None:
    """Map a local sector label onto the harmonised 11-sector scheme."""
    if local is None or (isinstance(local, float)):
        return None
    if scheme == "GICS":
        return local if local in HARMONISED_SECTORS else None
    m = SECTOR_MAPS.get(scheme, {})
    return m.get(str(local).strip())


def _clean(o):
    """Recursively replace NaN/inf floats with None so the JSON is strictly valid."""
    import math
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_clean(obj), f, ensure_ascii=False, separators=(",", ":"), default=_json_default, allow_nan=False)


def _json_default(o):
    import numpy as np
    import pandas as pd

    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        return None if v != v else v
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.strftime("%Y-%m-%d")
    if isinstance(o, (np.ndarray,)):
        return o.tolist()
    if isinstance(o, float) and o != o:
        return None
    raise TypeError(f"not serialisable: {type(o)}")
