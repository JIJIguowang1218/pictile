#!/usr/bin/env python3
"""Run T01: baseline_v0 outputs + structural checks + human rating sheet.

T01 structural output is automatic. Quality verdicts are NOT assigned here:
every structurally valid image is marked `review` until the owner fills
out/T01/<batch>/rating.csv and runs scripts/aggregate_t01.py.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "tools"))

import common  # noqa: E402
from pictile.pipeline import run_baseline  # noqa: E402
from pictile.render import render_csv, render_pdf, render_preview  # noqa: E402

A4_W, A4_H = 595.276, 841.890
FAILURE_HELP = (
    "eye_lost, text_unreadable, outline_blur, island_noise, skin_shift, banding, "
    "background_clutter, subject_too_small, thin_line_lost, color_shift, detail_lost, other"
)


def now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def unique(items):
    out = []
    for x in items:
        if x not in out:
            out.append(x)
    return out


def group_of(img_type: str) -> str:
    if img_type == "hard_negative":
        return "硬负例"
    if img_type == "other":
        return "未分类"
    return "正例"


def overview(items: list[dict], path: Path) -> None:
    if not items:
        return
    cols, cell, label = 6, 200, 30
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        x, y = c * cell, r * (cell + label)
        with Image.open(it["preview"]) as im:
            im = im.convert("RGB")
            im.thumbnail((cell - 8, cell - 8), Image.LANCZOS)
            sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        d.text((x + 4, y + cell + 6), it["image_id"].split("-")[-1], font=font, fill=(20, 20, 20))
    sheet.save(path, quality=85)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run T01 baseline outputs and rating sheet.")
    ap.add_argument("--batch", required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "T01")
    ap.add_argument("--n-colors", type=int, default=12)
    ap.add_argument("--grid", type=int, default=29)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--images-root", type=Path, default=None)
    ap.add_argument("--palette", type=Path, default=None)
    args = ap.parse_args()

    sd = common.stage_dir("T01")
    manifest_path = common.TESTS / "manifests" / sd / f"{args.batch}.json"
    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")
    manifest = common.load_json(manifest_path)
    images_root = common.resolve_images_root(args.images_root)
    result_dir = common.TESTS / "results" / sd / args.batch
    result_dir.mkdir(parents=True, exist_ok=True)
    out_dir = args.out / args.batch
    out_dir.mkdir(parents=True, exist_ok=True)
    review_dir = common.TESTS / "reviews" / sd
    review_dir.mkdir(parents=True, exist_ok=True)

    run_id = f"R{args.batch}-v0"
    variant = f"{args.grid}x{args.grid}_{args.n_colors}c_area_mard221_v0"
    images = list(manifest.get("images", []))
    if args.limit:
        images = images[: args.limit]

    summary = []
    structural_failures = Counter()
    type_counts = Counter()
    group_counts = Counter()

    for n, img in enumerate(images, 1):
        image_id = img["image_id"]
        group = group_of(img.get("type", ""))
        group_counts[group] += 1
        type_counts[img.get("type", "unknown")] += 1
        image_path = common.resolve_image_path(img["path"], images_root)
        item_dir = out_dir / image_id
        item_dir.mkdir(parents=True, exist_ok=True)

        t0 = time.perf_counter()
        failures: list[str] = []
        metrics: dict = {}
        try:
            res = run_baseline(
                image_path,
                image_id=image_id,
                palette_path=args.palette,
                n_colors=args.n_colors,
                grid_size=args.grid,
            )
            preview_path = item_dir / "preview.png"
            pdf_path = item_dir / "pattern.pdf"
            csv_path = item_dir / "usage.csv"
            meta_path = item_dir / "meta.json"

            render_preview(res.mapped_rgb, preview_path)
            pdf_meta = render_pdf(
                res.codes,
                res.mapped_rgb,
                pdf_path,
                image_id=image_id,
                palette_name=res.metrics.get("palette", "mard221"),
                colors_used=res.metrics["colors_used"],
                beads_total=res.metrics["beads_total"],
            )
            render_csv(res.used, csv_path)

            if res.metrics["grid"] != [args.grid, args.grid]:
                failures.append("grid_mismatch")
            if res.metrics["cells_total"] != args.grid * args.grid:
                failures.append("cell_count_mismatch")
            if res.metrics["colors_used"] > args.n_colors:
                failures.append("color_count_exceeded")
            used_codes = {u["code"] for u in res.used}
            if not used_codes.issubset(res.palette_codes):
                failures.append("invalid_color")

            csv_cells = 0
            csv_rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig", newline="")))
            for row in csv_rows:
                csv_cells += int(row["cells"])
                if int(row["beads_incl_10pct"]) != math.ceil(int(row["cells"]) * 1.1):
                    failures.append("csv_mismatch")
            if csv_cells != args.grid * args.grid:
                failures.append("csv_mismatch")
            if len(csv_rows) != res.metrics["colors_used"]:
                failures.append("csv_mismatch")

            if not preview_path.exists() or preview_path.stat().st_size == 0:
                failures.append("missing_export")
            if not csv_path.exists() or csv_path.stat().st_size == 0:
                failures.append("missing_export")
            if not pdf_path.exists() or pdf_path.stat().st_size == 0:
                failures.append("missing_export")
            else:
                raw = pdf_path.read_bytes()
                if not raw.startswith(b"%PDF"):
                    failures.append("pdf_invalid")
                else:
                    m = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([0-9.]+)\s+([0-9.]+)\s*\]", raw)
                    if not m:
                        failures.append("pdf_invalid")
                    else:
                        pw, ph = float(m.group(1)), float(m.group(2))
                        if abs(pw - A4_W) > 2 or abs(ph - A4_H) > 2:
                            failures.append("pdf_invalid")
            if pdf_meta.get("page") != "A4" or pdf_meta.get("pages") != 1:
                failures.append("pdf_invalid")
            if pdf_meta.get("ruler_mm") != 10.0 or pdf_meta.get("cell_mm") != 5.0:
                failures.append("pdf_invalid")

            total_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            metrics = dict(res.metrics)
            metrics.update({
                "group": group,
                "type": img.get("type", ""),
                "total_ms": total_ms,
                "csv_cells_total": csv_cells,
                "pdf": pdf_meta,
                "structural_failures": unique(failures),
                "files": {
                    "preview": f"{image_id}/preview.png",
                    "pdf": f"{image_id}/pattern.pdf",
                    "csv": f"{image_id}/usage.csv",
                },
            })
            meta_payload = {
                "image_id": image_id,
                "type": img.get("type"),
                "group": group,
                "source_url": img.get("source_url", ""),
                "license": img.get("license", ""),
                "run_id": run_id,
                "variant": variant,
                "metrics": metrics,
                "structural_failures": unique(failures),
            }
            meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            (item_dir / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            failures.append("pipeline_error")
            metrics = {
                "group": group,
                "type": img.get("type", ""),
                "error": f"{type(exc).__name__}: {exc}",
                "total_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            }
            print(f"ERROR {image_id}: {exc}")

        for f in failures:
            structural_failures[f] += 1

        verdict = "fail" if failures else "review"
        comment = "T01 structural pass; pending human rating." if not failures else (
            "T01 structural failure: " + ", ".join(unique(failures))
        )

        result_path = result_dir / f"{image_id}.json"
        data = common.load_json(result_path) if result_path.exists() else {
            "image_id": image_id, "path": img["path"], "sha256": img["sha256"], "runs": []
        }
        old = next((r for r in data.get("runs", []) if r.get("run_id") == run_id), None)
        preserved = old if old and "rating" in (old.get("metrics") or {}) else None

        new_metrics = metrics
        if preserved:
            new_metrics.update({
                "rating": preserved["metrics"]["rating"],
                "group": preserved["metrics"].get("group", group),
            })
            verdict = preserved["verdict"]
            failures = preserved["failures"]
            comment = preserved["comment"]
            reviewer = preserved["reviewer"]
        else:
            reviewer = "zcode"

        runs = [r for r in data.get("runs", []) if r.get("run_id") != run_id]
        runs.append({
            "run_id": run_id,
            "variant": variant,
            "date": now_date(),
            "verdict": verdict,
            "metrics": new_metrics,
            "failures": unique(failures),
            "comment": comment,
            "reviewer": reviewer,
            "updated_at": now_iso(),
        })
        data["runs"] = runs
        common.write_json(result_path, data)

        summary.append({
            "image_id": image_id,
            "group": group,
            "type": img.get("type", ""),
            "rating": preserved["metrics"]["rating"] if preserved else "",
            "failures": ";".join(preserved["failures"]) if preserved else "",
            "comment": preserved["comment"] if preserved else "",
            "preview": f"{image_id}/preview.png",
            "pdf": f"{image_id}/pattern.pdf",
            "csv": f"{image_id}/usage.csv",
        })
        print(f"[{n}/{len(images)}] {image_id} {group} {verdict} "
              f"colors={new_metrics.get('colors_used','-')} {new_metrics.get('total_ms','-')}ms")

    # rating sheet (never overwrite an existing filled sheet)
    rating_path = out_dir / "rating.csv"
    if not rating_path.exists():
        with rating_path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["image_id", "组别", "类型", "评分", "失败标签", "评论",
                                              "预览", "PDF", "CSV"])
            w.writeheader()
            for s in summary:
                w.writerow({
                    "image_id": s["image_id"],
                    "组别": s["group"],
                    "类型": s["type"],
                    "评分": s["rating"],
                    "失败标签": s["failures"],
                    "评论": s["comment"],
                    "预览": s["preview"],
                    "PDF": s["pdf"],
                    "CSV": s["csv"],
                })
        print(f"wrote {rating_path}")
    else:
        print(f"rating sheet exists, not overwritten: {rating_path}")

    readme = out_dir / "rating_readme.md"
    readme.write_text(f"""# T01 人工评分说明

## 样本
- 总图片：{len(images)}（正例 {group_counts.get('正例',0)}、硬负例 {group_counts.get('硬负例',0)}、未分类 {group_counts.get('未分类',0)}）
- 类型：{', '.join(f'{k} {v}' for k, v in sorted(type_counts.items()))}
- 变体：`{variant}`

## 怎么评
1. 打开 `preview.png` 或 `pattern.pdf`，先缩到约 3cm 看一眼，再给分。
2. 在 `rating.csv` 的 **评分** 列填 1–5 的整数。
3. **失败标签** 用分号分隔，可多选；可用的值：`{FAILURE_HELP}`。
4. **评论** 可选，写一两句原因。

## 1–5 分
1. 完全认不出，拼出来是废图。
2. 勉强能看出轮廓，关键特征丢失。
3. 需要努力才能认出，有明显缺陷。
4. 能认出，只有轻微缺陷。
5. 一眼认出，在这个尺寸下可以接受。

## 分组
- **正例**：参与平均分。目标：平均 ≥3.5，中位数 ≥3.5，≥70% 的图 ≥3，且每个大类（样本 ≥3）平均 ≥2.5。
- **硬负例**：不参与平均分。只看是否记录了失败模式、是否结构正常。
- **未分类**：暂不参与平均分。

## 评完后
```bash
python scripts/aggregate_t01.py --batch {args.batch}
```
""", encoding="utf-8")

    # overview of previews
    overview([{**s, "preview": str(out_dir / s["preview"])} for s in summary], out_dir / "overview.jpg")

    # batch structural review
    pass_n = sum(1 for s in summary if s["rating"] == "" and not s["failures"])
    review_path = review_dir / f"{args.batch}.md"
    lines = [
        f"# T01 / {args.batch} 结构与运行总结",
        "",
        f"- 样本：{len(summary)} 张",
        f"- 分组：正例 {group_counts.get('正例',0)} / 硬负例 {group_counts.get('硬负例',0)} / 未分类 {group_counts.get('未分类',0)}",
        f"- 类型：{', '.join(f'{k} {v}' for k, v in sorted(type_counts.items()))}",
        f"- 变体：`{variant}`",
        f"- 结构失败：{sum(structural_failures.values())} 项" + (
            f"（{', '.join(f'{k}×{v}' for k, v in structural_failures.items())}）" if structural_failures else "（无）"
        ),
        "",
        "## 验收标准",
        "",
        "结构与 T00 相同：29×29、841 格、≤12 色、色号都在 MARD 221、CSV 一致、PDF A4 单页 5mm/格 10mm 标尺。",
        "质量评分不在这里做，见 `out/T01/{}/rating.csv`。".format(args.batch),
        "",
        "## 产物",
        "",
        f"- 输出：`{out_dir.as_posix()}`",
        f"- 评分表：`{(out_dir / 'rating.csv').as_posix()}`",
        f"- 总览：`{(out_dir / 'overview.jpg').as_posix()}`",
        "",
        "## 下一步",
        "",
        "填 `rating.csv` 的评分/失败标签/评论，然后运行 `python scripts/aggregate_t01.py --batch {}`。".format(args.batch),
    ]
    review_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nstructural failures: {sum(structural_failures.values())}")
    print(f"outputs: {out_dir}")
    print(f"rating:  {rating_path}")
    print(f"review:  {review_path}")
    return 0 if sum(structural_failures.values()) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
