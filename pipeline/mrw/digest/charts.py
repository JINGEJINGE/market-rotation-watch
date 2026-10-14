"""PNG charts for the Telegram push: cross-market heatmap and an RRG scatter.
Palette: diverging blue <-> red with a neutral gray midpoint; categorical slots in fixed order."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402

from ..config import MARKETS  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MARKET_COLOR = dict(zip(["US", "KR", "HK", "JP", "TW"], CAT[:5]))
DIVERGING = LinearSegmentedColormap.from_list("mrw_div", ["#104281", "#2a78d6", "#9ec5f4", "#f0efec", "#f3a8a7", "#e34948", "#8f1f1f"])


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c3c2b7")
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def heatmap_png(out: dict, path: Path, metric: str = "residual_5d_z", title: str | None = None) -> Path:
    hm = out["heatmap"]
    vals = np.array([[np.nan if v is None else v for v in row] for row in hm["values"][metric]], dtype=float)
    fig, ax = plt.subplots(figsize=(7.2, 5.6), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    lim = np.nanmax(np.abs(vals)) if np.isfinite(vals).any() else 1
    lim = max(0.5, min(lim, 3.0))
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim)
    ax.imshow(np.nan_to_num(vals, nan=0.0), cmap=DIVERGING, norm=norm, aspect="auto")
    ax.set_xticks(range(len(hm["markets"])))
    ax.set_xticklabels([MARKETS[m]["name"] for m in hm["markets"]], fontsize=9, color=INK)
    ax.set_yticks(range(len(hm["sectors"])))
    ax.set_yticklabels(hm["sectors"], fontsize=9, color=INK)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            v = vals[i, j]
            if np.isnan(v):
                ax.text(j, i, "·", ha="center", va="center", color=MUTED, fontsize=9)
            else:
                ax.text(j, i, f"{v:+.1f}", ha="center", va="center", fontsize=8.5,
                        color="#ffffff" if abs(v) > 0.6 * lim else INK)
    # white gaps between cells
    ax.set_xticks(np.arange(-0.5, vals.shape[1], 1), minor=True)
    ax.set_yticks(np.arange(-0.5, vals.shape[0], 1), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.tick_params(which="minor", length=0)
    stamp = max(out["meta"]["as_of"].values())
    ax.set_title(title or f"Beta-adjusted 5-day relative return, z-score · {stamp}", fontsize=10.5, color=INK, loc="left", pad=10)
    fig.text(0.01, 0.01, "Market Rotation Watch · blue = capital rotating out, red = rotating in · cap-weighted, local currency",
             fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def rrg_png(out: dict, path: Path, types: tuple[str, ...] = ("sector",), markets: tuple[str, ...] | None = None,
            title: str | None = None) -> Path:
    bs = [b for b in out["baskets"] if b["type"] in types and b["rs_ratio"] is not None
          and (markets is None or b["market"] in markets)]
    fig, ax = plt.subplots(figsize=(7.2, 6.4), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    ax.axhline(100, color="#c3c2b7", linewidth=1)
    ax.axvline(100, color="#c3c2b7", linewidth=1)
    for b in bs:
        col = MARKET_COLOR.get(b["market"], CAT[6])
        trail = [(x, y) for x, y in b["series"]["rrg_trail"][-6:] if x is not None and y is not None]
        if len(trail) >= 2:
            xs, ys = zip(*trail)
            ax.plot(xs, ys, color=col, linewidth=1.0, alpha=0.35)
        ax.scatter([b["rs_ratio"]], [b["rs_mom"]], s=42, color=col, edgecolor=SURFACE, linewidth=1.2, zorder=3)
        ax.annotate(b["name"] if b["type"] != "sector" else f"{b['market']} {b['name'][:14]}", (b["rs_ratio"], b["rs_mom"]),
                    xytext=(4, 3), textcoords="offset points", fontsize=6.5, color=INK2)
    lim_x = max(1.5, max(abs(b["rs_ratio"] - 100) for b in bs) + 0.4) if bs else 2
    lim_y = max(1.5, max(abs(b["rs_mom"] - 100) for b in bs) + 0.4) if bs else 2
    ax.set_xlim(100 - lim_x, 100 + lim_x)
    ax.set_ylim(100 - lim_y, 100 + lim_y)
    for txt, (x, y) in {"Leading": (0.98, 0.98), "Weakening": (0.98, 0.02), "Lagging": (0.02, 0.02), "Improving": (0.02, 0.98)}.items():
        ax.text(x, y, txt, transform=ax.transAxes, fontsize=9, color=MUTED, ha="right" if x > 0.5 else "left",
                va="top" if y > 0.5 else "bottom")
    ax.set_xlabel("RS-Ratio (relative strength vs own benchmark, 63d)", fontsize=8.5, color=INK2)
    ax.set_ylabel("RS-Momentum (21d)", fontsize=8.5, color=INK2)
    for m, c in MARKET_COLOR.items():
        if markets is None or m in markets:
            ax.scatter([], [], color=c, label=MARKETS[m]["name"], s=30)
    ax.legend(frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=5)
    stamp = max(out["meta"]["as_of"].values())
    ax.set_title(title or f"Relative rotation, 5-day trails · {stamp}", fontsize=10.5, color=INK, loc="left", pad=28)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path
