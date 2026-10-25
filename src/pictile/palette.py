"""Palette loading, Lab conversion, CIEDE2000, and fixed-palette subset selection."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.strip().lstrip("#")
    if len(v) != 6:
        raise ValueError(f"invalid hex color: {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def rgb_to_lab(rgb) -> np.ndarray:
    """sRGB (0..255) to CIELAB (D65) using OpenCV.

    Accepts (3,), (N,3) or (H,W,3); returns the same leading shape.
    """
    arr = np.asarray(rgb, dtype=np.float32) / 255.0
    if arr.ndim == 1:
        return cv2.cvtColor(arr.reshape(1, 1, 3), cv2.COLOR_RGB2LAB)[0, 0].astype(np.float64)
    if arr.ndim == 2:
        return cv2.cvtColor(arr.reshape(1, -1, 3), cv2.COLOR_RGB2LAB)[0].astype(np.float64)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2LAB).astype(np.float64)


def delta_e_2000_matrix(lab_a: np.ndarray, lab_b: np.ndarray) -> np.ndarray:
    """CIEDE2000 between every row of lab_a and every row of lab_b -> (N, M)."""
    a = np.asarray(lab_a, dtype=np.float64).reshape(-1, 3)
    b = np.asarray(lab_b, dtype=np.float64).reshape(-1, 3)
    L1, a1, b1 = a[:, None, 0], a[:, None, 1], a[:, None, 2]
    L2, a2, b2 = b[None, :, 0], b[None, :, 1], b[None, :, 2]

    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cbar = (C1 + C2) / 2.0
    Cbar7 = Cbar ** 7
    G = 0.5 * (1.0 - np.sqrt(Cbar7 / (Cbar7 + 25.0 ** 7)))
    a1p = (1.0 + G) * a1
    a2p = (1.0 + G) * a2
    C1p = np.hypot(a1p, b1)
    C2p = np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0

    dLp = L2 - L1
    dCp = C2p - C1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180.0, dhp - 360.0, dhp)
    dhp = np.where(dhp < -180.0, dhp + 360.0, dhp)
    dHp = 2.0 * np.sqrt(np.maximum(C1p * C2p, 0.0)) * np.sin(np.radians(dhp / 2.0))

    Lbarp = (L1 + L2) / 2.0
    Cbarp = (C1p + C2p) / 2.0
    hsum = h1p + h2p
    hdiff = np.abs(h1p - h2p)
    hbarp = np.where(
        hdiff <= 180.0,
        hsum / 2.0,
        np.where(hsum < 360.0, (hsum + 360.0) / 2.0, (hsum - 360.0) / 2.0),
    )
    hbarp = np.where((C1p * C2p) == 0.0, hsum, hbarp)

    T = (
        1.0
        - 0.17 * np.cos(np.radians(hbarp - 30.0))
        + 0.24 * np.cos(np.radians(2.0 * hbarp))
        + 0.32 * np.cos(np.radians(3.0 * hbarp + 6.0))
        - 0.20 * np.cos(np.radians(4.0 * hbarp - 63.0))
    )
    dtheta = 30.0 * np.exp(-((hbarp - 275.0) / 25.0) ** 2)
    Cbarp7 = Cbarp ** 7
    Rc = 2.0 * np.sqrt(Cbarp7 / (Cbarp7 + 25.0 ** 7))
    SL = 1.0 + 0.015 * (Lbarp - 50.0) ** 2 / np.sqrt(20.0 + (Lbarp - 50.0) ** 2)
    SC = 1.0 + 0.045 * Cbarp
    SH = 1.0 + 0.015 * Cbarp * T
    RT = -np.sin(np.radians(2.0 * dtheta)) * Rc

    return np.sqrt(
        (dLp / SL) ** 2
        + (dCp / SC) ** 2
        + (dHp / SH) ** 2
        + RT * (dCp / SC) * (dHp / SH)
    )


def delta_e_2000(lab1, lab2) -> float:
    return float(delta_e_2000_matrix(np.asarray(lab1).reshape(1, 3), np.asarray(lab2).reshape(1, 3))[0, 0])


@dataclass
class Palette:
    codes: list[str]
    names: list[str]
    hexes: list[str]
    rgb: np.ndarray
    lab: np.ndarray
    source: str

    def index_of(self, code: str) -> int:
        return self.codes.index(code)


def load_palette(path: str | Path) -> Palette:
    path = Path(path)
    codes, names, hexes, rgbs = [], [], [], []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            code = (row.get("code") or "").strip()
            hexv = (row.get("hex") or "").strip()
            if not code or not hexv:
                continue
            codes.append(code)
            names.append((row.get("name") or "").strip())
            hexes.append(hexv.upper())
            rgbs.append(hex_to_rgb(hexv))
    if not codes:
        raise ValueError(f"empty palette: {path}")
    rgb = np.asarray(rgbs, dtype=np.uint8)
    return Palette(codes, names, hexes, rgb, rgb_to_lab(rgb), path.as_posix())


def select_subset(
    cell_lab: np.ndarray,
    palette_lab: np.ndarray,
    n: int = 12,
    weights: np.ndarray | None = None,
    refine_passes: int = 1,
) -> list[int]:
    """Greedy facility-location selection + swap refinement.

    Minimizes sum_i w_i * min_c dE(cell_i, palette_c).
    """
    cell_lab = np.asarray(cell_lab, dtype=np.float64).reshape(-1, 3)
    palette_lab = np.asarray(palette_lab, dtype=np.float64).reshape(-1, 3)
    dist = delta_e_2000_matrix(cell_lab, palette_lab)  # (N, M)
    N, M = dist.shape
    w = np.ones(N, dtype=np.float64) if weights is None else np.asarray(weights, dtype=np.float64).reshape(-1)
    n = max(1, min(int(n), M))

    selected: list[int] = []
    current = np.full(N, np.inf)
    for _ in range(n):
        best_c = -1
        best_total = np.inf
        for c in range(M):
            if c in selected:
                continue
            total = float(np.sum(w * np.minimum(current, dist[:, c])))
            if total < best_total:
                best_total = total
                best_c = c
        if best_c < 0:
            break
        selected.append(best_c)
        current = np.minimum(current, dist[:, best_c])

    if refine_passes > 0 and len(selected) < M:
        def total_for(sel: list[int]) -> float:
            return float(np.sum(w * np.min(dist[:, sel], axis=1)))

        best = total_for(selected)
        for _ in range(refine_passes):
            improved = False
            selected_set = set(selected)
            for i in range(len(selected)):
                for c in range(M):
                    if c in selected_set:
                        continue
                    trial = selected.copy()
                    trial[i] = c
                    t = total_for(trial)
                    if t < best - 1e-9:
                        selected = trial
                        best = t
                        selected_set = set(selected)
                        improved = True
            if not improved:
                break
    return selected


def map_cells(cell_lab: np.ndarray, palette_lab: np.ndarray, selected: list[int]) -> tuple[np.ndarray, np.ndarray]:
    sel = np.asarray(selected, dtype=int)
    dist = delta_e_2000_matrix(cell_lab, palette_lab[sel])
    idx = np.argmin(dist, axis=1)
    return sel[idx], dist[np.arange(len(idx)), idx]
