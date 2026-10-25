"""baseline_v0: deterministic image -> 29x29 -> MARD subset -> mapped grid."""
from __future__ import annotations

import collections
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .imaging import load_square_rgb
from .palette import load_palette, map_cells, rgb_to_lab, select_subset
from .render import bead_count

DEFAULT_PALETTE = Path(__file__).resolve().parent / "data" / "mard221.csv"


@dataclass
class BaselineResult:
    image_id: str
    grid_size: int
    codes: np.ndarray
    mapped_rgb: np.ndarray
    used: list[dict]
    metrics: dict
    palette_codes: set[str]
    image_meta: dict = field(default_factory=dict)


def run_baseline(
    image_path: str | Path,
    image_id: str,
    palette_path: str | Path | None = None,
    n_colors: int = 12,
    grid_size: int = 29,
) -> BaselineResult:
    t0 = time.perf_counter()
    cell_rgb, image_meta = load_square_rgb(image_path, grid_size)
    palette = load_palette(palette_path or DEFAULT_PALETTE)
    cell_lab = rgb_to_lab(cell_rgb.reshape(-1, 3))

    selected = select_subset(cell_lab, palette.lab, n=n_colors)
    idx, dist = map_cells(cell_lab, palette.lab, selected)

    codes = np.asarray(palette.codes)[idx].reshape(grid_size, grid_size)
    mapped_rgb = palette.rgb[idx].reshape(grid_size, grid_size, 3)

    counts = collections.Counter(codes.flatten().tolist())
    used: list[dict] = []
    for code, cells in counts.most_common():
        i = palette.index_of(code)
        beads = bead_count(cells)
        used.append({
            "code": code,
            "name": palette.names[i],
            "hex": palette.hexes[i],
            "cells": int(cells),
            "beads": int(beads),
            "bags": int(math.ceil(beads / 1000.0)),
        })

    beads_total = sum(u["beads"] for u in used)
    metrics = {
        "grid": [grid_size, grid_size],
        "cells_total": int(grid_size * grid_size),
        "colors_used": len(used),
        "selected_codes": [palette.codes[i] for i in selected],
        "delta_e_p50": float(np.percentile(dist, 50)),
        "delta_e_p95": float(np.percentile(dist, 95)),
        "delta_e_max": float(np.max(dist)),
        "beads_total": int(beads_total),
        "compute_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        "image_meta": image_meta,
        "palette": Path(palette_path or DEFAULT_PALETTE).name,
    }
    return BaselineResult(
        image_id=image_id,
        grid_size=grid_size,
        codes=codes,
        mapped_rgb=mapped_rgb,
        used=used,
        metrics=metrics,
        palette_codes=set(palette.codes),
        image_meta=image_meta,
    )
