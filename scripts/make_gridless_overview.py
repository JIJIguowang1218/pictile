#!/usr/bin/env python3
"""Generate gridless previews and a contact sheet for a T01 batch."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "tools"))

import common  # noqa: E402
from pictile.pipeline import run_baseline  # noqa: E402
from pictile.render import render_preview  # noqa: E402

TYPE_CN = {
    "cartoon": "卡通", "portrait": "人物", "pet": "宠物", "logo": "Logo",
    "product": "产品", "scene": "风景", "text": "文字", "screenshot": "截图",
    "hard_negative": "硬负例", "other": "其他",
}
SCORE_COLOR = {
    1: (220, 38, 38), 2: (234, 88, 12), 3: (217, 119, 6),
    4: (22, 163, 74), 5: (21, 128, 61), None: (107, 114, 128),
}


def font(size: int):
    for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def main() -> int:
    ap = argparse.ArgumentParser(description="Gridless previews + overview for a batch.")
    ap.add_argument("--stage", default="T01")
    ap.add_argument("--batch", required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--cell", type=int, default=200)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--n-colors", type=int, default=12)
    ap.add_argument("--grid", type=int, default=29)
    ap.add_argument("--images-root", type=Path, default=None)
    ap.add_argument("--palette", type=Path, default=None)
    args = ap.parse_args()

    sd = common.stage_dir(args.stage)
    manifest_path = common.TESTS / "manifests" / sd / f"{args.batch}.json"
    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")
    manifest = common.load_json(manifest_path)
    out_dir = (args.out or (ROOT / "out" / args.stage / args.batch)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    images_root = common.resolve_images_root(args.images_root)

    rating_path = out_dir / "rating.csv"
    rating = {}
    if rating_path.exists():
        with rating_path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                raw = (row.get("评分") or "").strip()
                rating[row.get("image_id")] = {
                    "score": int(float(raw)) if raw else None,
                    "type": row.get("类型") or "",
                    "group": row.get("组别") or "",
                }

    items = []
    total = len(manifest.get("images", []))
    for n, img in enumerate(manifest.get("images", []), 1):
        image_id = img["image_id"]
        image_path = common.resolve_image_path(img["path"], images_root)
        res = run_baseline(
            image_path,
            image_id=image_id,
            palette_path=args.palette,
            n_colors=args.n_colors,
            grid_size=args.grid,
        )
        gridless = out_dir / image_id / "preview_gridless.png"
        render_preview(res.mapped_rgb, gridless, cell_px=20, grid_lines=False)
        info = rating.get(image_id, {})
        items.append({
            "image_id": image_id,
            "score": info.get("score"),
            "type": info.get("type") or img.get("type", ""),
            "group": info.get("group", ""),
            "path": gridless,
        })
        print(f"[{n}/{total}] {image_id} score={items[-1]['score']}")

    cols = args.cols
    cell = args.cell
    label_h = 36
    banner = 56
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, banner + rows * (cell + label_h)), (245, 246, 248))
    d = ImageDraw.Draw(sheet)
    d.text((16, 16), f"pictile {args.stage} · {args.grid}×{args.grid} · 去除格线 · {len(items)} 张",
           font=font(20), fill=(17, 24, 39))
    d.text((16, 38), "分数 1–5（红→绿）；无格线只显示色块", font=font(12), fill=(107, 114, 128))

    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        x = c * cell
        y = banner + r * (cell + label_h)
        with Image.open(it["path"]) as im:
            im = im.convert("RGB")
            im.thumbnail((cell - 12, cell - 12), Image.LANCZOS)
            tile = Image.new("RGB", (cell - 12, cell - 12), (255, 255, 255))
            tile.paste(im, ((tile.width - im.width) // 2, (tile.height - im.height) // 2))
            sheet.paste(tile, (x + 6, y + 6))
        d.rectangle([x + 5, y + 5, x + cell - 7, y + cell - 7], outline=(210, 214, 220), width=1)
        score = it["score"]
        color = SCORE_COLOR.get(score, SCORE_COLOR[None])
        d.rounded_rectangle([x + 6, y + cell + 7, x + 26, y + cell + 27], radius=4, fill=color)
        d.text((x + 11, y + cell + 8), str(score if score is not None else "?"),
               font=font(13), fill=(255, 255, 255))
        label = f'{it["image_id"].split("-")[-1]} · {TYPE_CN.get(it["type"], it["type"])}'
        d.text((x + 32, y + cell + 8), label, font=font(13), fill=(31, 41, 55))

    overview = out_dir / "overview_gridless.jpg"
    sheet.save(overview, quality=90)
    print(f"\nwrote {overview}")
    print(f"gridless previews: {out_dir}/<image_id>/preview_gridless.png")
    print(f"size: {sheet.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
