#!/usr/bin/env python3
"""Run a size variant (e.g., 58x58) on the T01 images and make comparison overviews.

Same images, same MARD 221 palette, same <=12 colors, same crop/pipeline.
Only the grid size changes. Outputs go to out/T01/<batch>/size_<grid>/ and do not
modify the formal T01 results.
"""
from __future__ import annotations

import argparse
import csv
import statistics
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
SCORE_COLOR = {1: (220, 38, 38), 2: (234, 88, 12), 3: (217, 119, 6), 4: (22, 163, 74), 5: (21, 128, 61), None: (107, 114, 128)}


def font(size: int):
    for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def overview(items: list[dict], path: Path, title: str, cols: int = 6, cell: int = 200) -> None:
    label_h = 38
    banner = 58
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, banner + rows * (cell + label_h)), (245, 246, 248))
    d = ImageDraw.Draw(sheet)
    d.text((16, 14), title, font=font(20), fill=(17, 24, 39))
    d.text((16, 38), "分数为 29×29 版人工评分；新尺寸尚未评分；无格线", font=font(12), fill=(107, 114, 128))
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        x, y = c * cell, banner + r * (cell + label_h)
        with Image.open(it["path"]) as im:
            im = im.convert("RGB")
            im.thumbnail((cell - 12, cell - 12), Image.LANCZOS)
            tile = Image.new("RGB", (cell - 12, cell - 12), (255, 255, 255))
            tile.paste(im, ((tile.width - im.width) // 2, (tile.height - im.height) // 2))
            sheet.paste(tile, (x + 6, y + 6))
        d.rectangle([x + 5, y + 5, x + cell - 7, y + cell - 7], outline=(210, 214, 220), width=1)
        score = it.get("score")
        color = SCORE_COLOR.get(score, SCORE_COLOR[None])
        d.rounded_rectangle([x + 6, y + cell + 8, x + 26, y + cell + 28], radius=4, fill=color)
        d.text((x + 11, y + cell + 9), str(score if score is not None else "?"), font=font(13), fill=(255, 255, 255))
        d.text((x + 32, y + cell + 9),
               f'{it["image_id"].split("-")[-1]} · {TYPE_CN.get(it["type"], it["type"])}',
               font=font(13), fill=(31, 41, 55))
    sheet.save(path, quality=90)


def paired_sheet(items: list[dict], path: Path, grid: int) -> None:
    tile = 150
    pair_w = tile * 2 + 22
    pair_h = tile + 30
    cols = 3
    banner = 62
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * pair_w + 16, banner + rows * pair_h + 12), (245, 246, 248))
    d = ImageDraw.Draw(sheet)
    d.text((16, 14), f"29×29 vs {grid}×{grid} · 同图同色板 · 代表样本", font=font(20), fill=(17, 24, 39))
    d.text((16, 39), f"每对左 29、右 {grid}；分数为 29 版评分，{grid} 尚未评分；无格线", font=font(12), fill=(107, 114, 128))
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        x = 16 + c * pair_w
        y = banner + r * pair_h
        for j, (label, p) in enumerate((("29", it["p29"]), (str(grid), it["pvar"]))):
            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((tile, tile), Image.LANCZOS)
                tile_im = Image.new("RGB", (tile, tile), (255, 255, 255))
                tile_im.paste(im, ((tile - im.width) // 2, (tile - im.height) // 2))
                sheet.paste(tile_im, (x + j * (tile + 8), y))
            d.rectangle([x + j * (tile + 8) - 1, y - 1, x + j * (tile + 8) + tile, y + tile], outline=(200, 205, 212), width=1)
            d.text((x + j * (tile + 8) + 4, y + tile + 3), label, font=font(12), fill=(80, 88, 100))
        score = it.get("score")
        color = SCORE_COLOR.get(score, SCORE_COLOR[None])
        d.rounded_rectangle([x, y + tile + 3, x + 20, y + tile + 23], radius=4, fill=color)
        d.text((x + 5, y + tile + 4), str(score if score is not None else "?"), font=font(12), fill=(255, 255, 255))
        d.text((x + 25, y + tile + 4),
               f'{it["image_id"].split("-")[-1]} · {TYPE_CN.get(it["type"], it["type"])}',
               font=font(12), fill=(31, 41, 55))
    sheet.save(path, quality=90)


def main() -> int:
    ap = argparse.ArgumentParser(description="Size variant + comparison overviews.")
    ap.add_argument("--stage", default="T01")
    ap.add_argument("--batch", required=True)
    ap.add_argument("--grid", type=int, default=58)
    ap.add_argument("--n-colors", type=int, default=12)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--images-root", type=Path, default=None)
    ap.add_argument("--palette", type=Path, default=None)
    args = ap.parse_args()

    sd = common.stage_dir(args.stage)
    manifest_path = common.TESTS / "manifests" / sd / f"{args.batch}.json"
    manifest = common.load_json(manifest_path)
    base_out = (args.out or (ROOT / "out" / args.stage / args.batch)).resolve()
    vdir = base_out / f"size_{args.grid}"
    vdir.mkdir(parents=True, exist_ok=True)
    images_root = common.resolve_images_root(args.images_root)

    rating = {}
    with (base_out / "rating.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            raw = (row.get("评分") or "").strip()
            rating[row.get("image_id")] = {
                "score": int(float(raw)) if raw else None,
                "type": row.get("类型") or "",
                "group": row.get("组别") or "",
            }

    rows = []
    items = []
    total = len(manifest.get("images", []))
    for n, img in enumerate(manifest.get("images", []), 1):
        image_id = img["image_id"]
        image_path = common.resolve_image_path(img["path"], images_root)
        resvar = run_baseline(image_path, image_id=image_id, palette_path=args.palette,
                              n_colors=args.n_colors, grid_size=args.grid)
        pvar = vdir / image_id / "preview_gridless.png"
        pvar.parent.mkdir(parents=True, exist_ok=True)
        render_preview(resvar.mapped_rgb, pvar, cell_px=10, grid_lines=False)

        # 29 preview already exists from the gridless overview; regenerate if missing.
        p29 = base_out / image_id / "preview_gridless.png"
        if not p29.exists():
            p29.parent.mkdir(parents=True, exist_ok=True)
            res29 = run_baseline(image_path, image_id=image_id, palette_path=args.palette,
                                 n_colors=args.n_colors, grid_size=29)
            render_preview(res29.mapped_rgb, p29, cell_px=20, grid_lines=False)

        info = rating.get(image_id, {})
        typ = info.get("type") or img.get("type", "")
        m29 = {}
        meta29 = base_out / image_id / "meta.json"
        if meta29.exists():
            m29 = (common.load_json(meta29).get("metrics") or {})
        rows.append({
            "image_id": image_id,
            "type": typ,
            "group": info.get("group", ""),
            "score29": info.get("score"),
            "delta_e_p95_29": m29.get("delta_e_p95"),
            "delta_e_p95_var": resvar.metrics.get("delta_e_p95"),
            "colors_29": m29.get("colors_used"),
            "colors_var": resvar.metrics.get("colors_used"),
            "beads_29": m29.get("beads_total"),
            "beads_var": resvar.metrics.get("beads_total"),
            "total_ms_var": resvar.metrics.get("total_ms"),
        })
        items.append({"image_id": image_id, "type": typ, "score": info.get("score"),
                      "path": pvar, "p29": p29, "pvar": pvar})
        print(f"[{n}/{total}] {image_id} -> {args.grid} p95={resvar.metrics['delta_e_p95']:.1f}")

    summary = vdir / f"size_{args.grid}_summary.csv"
    with summary.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    overview(items, vdir / f"overview_{args.grid}_gridless.jpg",
             f"pictile {args.stage} · {args.grid}×{args.grid} · 去除格线 · {len(items)} 张")

    # Representative pairs: worst / median / best per type, plus 4 hard negatives.
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(it["type"], []).append(it)
    picks = []
    for t, arr in groups.items():
        arr = sorted(arr, key=lambda x: (x["score"] is None, x["score"]))
        if len(arr) >= 3:
            picks.extend([arr[0], arr[len(arr) // 2], arr[-1]])
        else:
            picks.extend(arr)
    # avoid too many: keep up to 3 per type, hard negatives 4
    hard = [x for x in items if x["type"] == "hard_negative"]
    picks = [x for x in picks if x["type"] != "hard_negative"] + hard[:4]
    paired_sheet(picks, vdir / f"paired_29_vs_{args.grid}.jpg", args.grid)

    # Automatic metric summary by type (informational, not human quality).
    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r["type"], []).append(r)
    print(f"\ntype | n | p95_29 | p95_{args.grid} | colors_29 | colors_{args.grid}")
    for t, arr in sorted(by_type.items()):
        p29 = [x["delta_e_p95_29"] for x in arr if x["delta_e_p95_29"] is not None]
        pvar = [x["delta_e_p95_var"] for x in arr if x["delta_e_p95_var"] is not None]
        print(f"{t} | {len(arr)} | {statistics.mean(p29):.1f} | {statistics.mean(pvar):.1f} | "
              f"{statistics.mean([x['colors_29'] for x in arr if x['colors_29'] is not None]):.1f} | "
              f"{statistics.mean([x['colors_var'] for x in arr if x['colors_var'] is not None]):.1f}")

    print(f"\nwrote {summary}")
    print(f"wrote {vdir / f'overview_{args.grid}_gridless.jpg'}")
    print(f"wrote {vdir / f'paired_29_vs_{args.grid}.jpg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
