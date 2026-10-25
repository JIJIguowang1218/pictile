#!/usr/bin/env python3
"""Scan the T01 staging folders, generate 清单.csv / 审查表.md / T01_总览.jpg.

The user drags images into Chinese type folders. This script preserves original
names and relative paths, assigns a stable number, and records sha256/size.
It does not rename or move anything.

  python scripts/scan_staging.py --staging "C:/Users/86136/Desktop/pictile_T00_待审核"
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
]
LAYOUTS = {
    "T01": [
        ("00_未分类", "未分类", "other", 0),
        ("01_卡通", "卡通", "cartoon", 15),
        ("02_人物", "人物", "portrait", 12),
        ("03_宠物", "宠物", "pet", 9),
        ("04_Logo", "Logo", "logo", 9),
        ("05_产品食物", "产品食物", "product", 4),
        ("06_风景", "风景", "scene", 2),
        ("07_文字", "文字", "text", 1),
        ("08_截图地图", "截图地图", "screenshot", 2),
        ("09_硬负例", "硬负例", "hard_negative", 6),
    ]
}


def font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_folder(staging: Path, prefix: str) -> Path | None:
    matches = [p for p in sorted(staging.glob(prefix + "*")) if p.is_dir()]
    return matches[0] if matches else None


def contact_sheet(items: list[dict], out: Path) -> None:
    if not items:
        return
    cell, label_h, cols = 240, 36, 5
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    f = font(20)
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        x, y = c * cell, r * (cell + label_h)
        im = Image.open(it["path"]).convert("RGBA")
        im.thumbnail((cell - 10, cell - 10), Image.LANCZOS)
        bg = Image.new("RGBA", (cell, cell), (255, 255, 255, 255))
        bg.alpha_composite(im, ((cell - im.width) // 2, (cell - im.height) // 2))
        sheet.paste(bg.convert("RGB"), (x, y))
        d.text((x + 6, y + cell + 8), f'{it["num"]} {it["chinese_type"]}', font=f, fill=(20, 20, 20))
    sheet.save(out, quality=88)


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan a T01 staging folder and make metadata.")
    ap.add_argument("--staging", type=Path, required=True)
    ap.add_argument("--stage", default="T01", choices=sorted(LAYOUTS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    staging = args.staging.resolve()
    if not staging.is_dir():
        raise SystemExit(f"not a directory: {staging}")
    out_manifest = staging / "清单.csv"
    if out_manifest.exists() and not args.dry_run:
        raise SystemExit(f"{out_manifest} exists; move it or rename it before rescanning")

    items: list[dict] = []
    counts: list[tuple[str, int, int]] = []
    bad_files: list[tuple[Path, str]] = []
    num = 0
    for prefix, chinese, final_type, expected in LAYOUTS[args.stage]:
        folder = resolve_folder(staging, prefix)
        if folder is None:
            counts.append((prefix, expected, 0))
            print(f"WARN missing folder {prefix}*")
            continue
        all_files = [p for p in sorted(folder.rglob("*")) if p.is_file()]
        files = [p for p in all_files if p.suffix.lower() in IMAGE_EXTS]
        others = [p for p in all_files if p.suffix.lower() not in IMAGE_EXTS]
        if others:
            print(f"INFO {folder.name}: ignored non-image {[p.name for p in others]}")
        valid = 0
        for p in files:
            try:
                with Image.open(p) as im:
                    size = f"{im.width}x{im.height}"
            except Exception as exc:  # noqa: BLE001
                bad_files.append((p, str(exc)))
                print(f"BAD  {p.relative_to(staging)}: {exc}")
                continue
            valid += 1
            num += 1
            items.append({
                "num": f"{num:02d}",
                "path": p,
                "rel": p.relative_to(staging).as_posix(),
                "name": p.name,
                "chinese_type": chinese,
                "final_type": final_type,
                "size": size,
                "sha256": sha256(p),
            })
        counts.append((folder.name, expected, valid))

    print("\ncounts (folder, expected, found):")
    for name, expected, found in counts:
        flag = "OK" if (expected == 0 or found >= expected) else "SHORT"
        print(f"  {name}: {found}/{expected} {flag}")
    print(f"total images: {len(items)}")

    if args.dry_run:
        print("dry-run: nothing written")
        return 0

    fields = ["编号", "临时文件名", "临时相对路径", "中文类型", "入库type", "说明",
              "来源URL", "下载URL", "作者/来源", "许可", "原始尺寸", "sha256", "审核状态", "备注"]
    with out_manifest.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for it in items:
            w.writerow({
                "编号": it["num"],
                "临时文件名": it["name"],
                "临时相对路径": it["rel"],
                "中文类型": it["chinese_type"],
                "入库type": it["final_type"],
                "说明": "",
                "来源URL": "",
                "下载URL": "",
                "作者/来源": "",
                "许可": "unknown",
                "原始尺寸": it["size"],
                "sha256": it["sha256"],
                "审核状态": "待审",
                "备注": "",
            })

    reviews = [
        "# T01 待审核清单",
        "",
        "先打开 `T01_总览.jpg` 看整体，再逐张决定。",
        "",
        "在 `清单.csv` 的 **审核状态** 列填 `通过` / `拒绝` / `替换`；在 **备注** 写原因。",
        "",
        "| 编号 | 文件 | 中文类型 | 入库 type | 尺寸 | 审核状态 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for it in items:
        reviews.append(
            f'| {it["num"]} | {it["rel"]} | {it["chinese_type"]} | {it["final_type"]} | {it["size"]} | 待审 |'
        )
    (staging / "审查表.md").write_text("\n".join(reviews) + "\n", encoding="utf-8")
    contact_sheet(items, staging / "T01_总览.jpg")

    print(f"\nwrote {out_manifest}")
    print(f"wrote {staging / '审查表.md'}")
    print(f"wrote {staging / 'T01_总览.jpg'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
