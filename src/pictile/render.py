"""Preview PNG, printable PDF, and usage CSV for the baseline pipeline."""
from __future__ import annotations

import csv
import math
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

A4_MM = (210.0, 297.0)


def render_preview(grid_rgb, path: str | Path, cell_px: int = 20, grid_lines: bool = True) -> None:
    h, w = grid_rgb.shape[:2]
    im = Image.new("RGB", (w * cell_px, h * cell_px), (255, 255, 255))
    d = ImageDraw.Draw(im)
    for y in range(h):
        for x in range(w):
            rgb = tuple(int(v) for v in grid_rgb[y, x])
            d.rectangle([x * cell_px, y * cell_px, (x + 1) * cell_px, (y + 1) * cell_px], fill=rgb)
    if not grid_lines:
        im.save(path)
        return
    for i in range(w + 1):
        color = (40, 40, 40) if i % 10 == 0 else ((90, 90, 90) if i % 5 == 0 else (160, 160, 160))
        width = 2 if i % 10 == 0 else 1
        d.line([(i * cell_px, 0), (i * cell_px, h * cell_px)], fill=color, width=width)
    for j in range(h + 1):
        color = (40, 40, 40) if j % 10 == 0 else ((90, 90, 90) if j % 5 == 0 else (160, 160, 160))
        width = 2 if j % 10 == 0 else 1
        d.line([(0, j * cell_px), (w * cell_px, j * cell_px)], fill=color, width=width)
    im.save(path)


def render_pdf(
    codes,
    mapped_rgb,
    path: str | Path,
    image_id: str,
    palette_name: str,
    colors_used: int,
    beads_total: int,
    cell_mm: float = 5.0,
) -> dict:
    h, w = codes.shape
    cell = cell_mm * mm
    grid_w = w * cell
    grid_h = h * cell
    x0 = (A4[0] - grid_w) / 2.0
    y0 = 90.0 * mm

    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"pictile {image_id}")
    c.setSubject(f"{w}x{h} / {palette_name} / {colors_used} colors")

    # cells
    for y in range(h):
        ypdf = y0 + (h - 1 - y) * cell
        for x in range(w):
            r, g, b = (int(v) / 255.0 for v in mapped_rgb[y, x])
            c.setFillColorRGB(r, g, b)
            c.rect(x0 + x * cell, ypdf, cell, cell, stroke=0, fill=1)

    # codes
    c.setFont("Helvetica", 4.2)
    for y in range(h):
        ypdf = y0 + (h - 1 - y) * cell
        for x in range(w):
            r, g, b = mapped_rgb[y, x]
            lum = (0.299 * int(r) + 0.587 * int(g) + 0.114 * int(b)) / 255.0
            c.setFillColorRGB(1, 1, 1) if lum < 0.45 else c.setFillColorRGB(0, 0, 0)
            c.drawCentredString(x0 + (x + 0.5) * cell, ypdf + cell * 0.32, str(codes[y, x]))

    # grid lines
    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    for i in range(w + 1):
        if i % 10 == 0:
            c.setLineWidth(1.2)
        elif i % 5 == 0:
            c.setLineWidth(0.7)
        else:
            c.setLineWidth(0.25)
        x = x0 + i * cell
        c.line(x, y0, x, y0 + grid_h)
    for j in range(h + 1):
        if j % 10 == 0:
            c.setLineWidth(1.2)
        elif j % 5 == 0:
            c.setLineWidth(0.7)
        else:
            c.setLineWidth(0.25)
        y = y0 + j * cell
        c.line(x0, y, x0 + grid_w, y)

    # row / column numbers
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 4.2)
    for i in range(w):
        c.drawCentredString(x0 + (i + 0.5) * cell, y0 + grid_h + 1.5 * mm, str(i + 1))
    for j in range(h):
        c.drawRightString(x0 - 1.5 * mm, y0 + (h - j - 0.5) * cell - 1.2 * mm, str(j + 1))

    # title
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x0, y0 + grid_h + 10 * mm, f"pictile — {image_id}")
    c.setFont("Helvetica", 7)
    c.drawString(
        x0,
        y0 + grid_h + 6 * mm,
        f"{w}x{h} grid · {cell_mm:g} mm/cell · {palette_name} · {colors_used} colors · {beads_total} beads (incl. 10% loss)",
    )

    # 10 mm ruler
    ruler_y = y0 - 25 * mm
    c.setLineWidth(0.8)
    c.line(x0, ruler_y, x0 + 10 * mm, ruler_y)
    for t in (0, 5, 10):
        c.line(x0 + t * mm, ruler_y - 1.2 * mm, x0 + t * mm, ruler_y + 1.2 * mm)
    c.setFont("Helvetica", 6.5)
    c.drawString(x0 + 12 * mm, ruler_y - 1.5 * mm, "10 mm ruler — verify 1:1 before printing")

    c.setFont("Helvetica", 6.5)
    c.drawString(x0, y0 - 38 * mm, "Print on A4 at 100% scale (no 'fit to page').")
    c.drawRightString(x0 + grid_w, y0 - 38 * mm, f"cell={cell_mm:g} mm")

    c.showPage()
    c.save()

    return {
        "page": "A4",
        "pages": 1,
        "page_mm": [A4_MM[0], A4_MM[1]],
        "grid": [int(w), int(h)],
        "cell_mm": cell_mm,
        "ruler_mm": 10.0,
    }


def render_csv(used: list[dict], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "name", "hex", "cells", "beads_incl_10pct", "bags_1000"])
        for row in used:
            w.writerow([row["code"], row["name"], row["hex"], row["cells"], row["beads"], row["bags"]])


def bead_count(cells: int, loss: float = 0.10) -> int:
    return int(math.ceil(cells * (1.0 + loss)))
