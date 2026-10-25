#!/usr/bin/env python3
"""Run the T00 structural smoke test over a batch and write results/review.

T00 is structural only: run, grid, color count, palette validity, exports.
It does NOT judge aesthetics; that is T01.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "tools"))

import common  # noqa: E402
from pictile.pipeline import run_baseline  # noqa: E402
from pictile.render import render_csv, render_pdf, render_preview  # noqa: E402

A4_W, A4_H = 595.276, 841.890


def now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def merged_test_metrics(failures: list[str]) -> list[str]:
    seen = []
    for f in failures:
        if f not in seen:
            seen.append(f)
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description="Run T00 structural smoke test.")
    ap.add_argument("--stage", default="T00")
    ap.add_argument("--batch", required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "T00")
    ap.add_argument("--n-colors", type=int, default=12)
    ap.add_argument("--grid", type=int, default=29)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--images-root", type=Path, default=None)
    ap.add_argument("--palette", type=Path, default=None)
    args = ap.parse_args()

    sd = common.stage_dir(args.stage)
    manifest_path = common.TESTS / "manifests" / sd / f"{args.batch}.json"
    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")
    manifest = common.load_json(manifest_path)
    images_root = common.resolve_images_root(args.images_root)
    result_dir = common.TESTS / "results" / sd / args.batch
    result_dir.mkdir(parents=True, exist_ok=True)
    out_dir = args.out / args.batch
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"R{args.batch}-v0"
    variant = f"{args.grid}x{args.grid}_{args.n_colors}c_area_mard221_v0"

    images = list(manifest.get("images", []))
    if args.limit:
        images = images[: args.limit]

    summary = []
    failures_by_type: dict[str, Counter] = defaultdict(Counter)
    all_failures: Counter = Counter()

    for n, img in enumerate(images, 1):
        image_id = img["image_id"]
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

            # ---- structural checks ----
            if res.metrics["grid"] != [args.grid, args.grid]:
                failures.append("grid_mismatch")
            if res.metrics["cells_total"] != args.grid * args.grid:
                failures.append("cell_count_mismatch")
            if res.metrics["colors_used"] > args.n_colors:
                failures.append("color_count_exceeded")
            used_codes = {u["code"] for u in res.used}
            if not used_codes.issubset(res.palette_codes):
                failures.append("invalid_color")

            # CSV must agree with the grid.
            csv_cells = 0
            csv_rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig", newline="")))
            for row in csv_rows:
                csv_cells += int(row["cells"])
            if csv_cells != args.grid * args.grid:
                failures.append("csv_mismatch")
            if len(csv_rows) != res.metrics["colors_used"]:
                failures.append("csv_mismatch")
            for row in csv_rows:
                if int(row["beads_incl_10pct"]) != math.ceil(int(row["cells"]) * 1.1):
                    failures.append("csv_mismatch")

            # Exports.
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
                "total_ms": total_ms,
                "csv_cells_total": csv_cells,
                "pdf": pdf_meta,
                "files": {
                    "preview": f"{image_id}/preview.png",
                    "pdf": f"{image_id}/pattern.pdf",
                    "csv": f"{image_id}/usage.csv",
                },
            })
            meta_payload = {
                "image_id": image_id,
                "type": img.get("type"),
                "source_url": img.get("source_url", ""),
                "license": img.get("license", ""),
                "run_id": run_id,
                "variant": variant,
                "metrics": metrics,
                "failures": merged_test_metrics(failures),
            }
            meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            (item_dir / "error.txt").write_text(tb, encoding="utf-8")
            failures.append("pipeline_error")
            metrics = {"error": f"{type(exc).__name__}: {exc}", "total_ms": round((time.perf_counter() - t0) * 1000.0, 1)}
            print(f"ERROR {image_id}: {exc}")

        verdict = "pass" if not failures else "fail"
        for f in failures:
            all_failures[f] += 1
            failures_by_type[img.get("type", "unknown")][f] += 1

        # update per-image result JSON
        result_path = result_dir / f"{image_id}.json"
        data = common.load_json(result_path) if result_path.exists() else {
            "image_id": image_id, "path": img["path"], "sha256": img["sha256"], "runs": []
        }
        runs = [r for r in data.get("runs", []) if r.get("run_id") != run_id]
        runs.append({
            "run_id": run_id,
            "variant": variant,
            "date": now_date(),
            "verdict": verdict,
            "metrics": metrics,
            "failures": merged_test_metrics(failures),
            "comment": "T00 structural smoke; no aesthetic rating." + (
                f" Issues: {', '.join(merged_test_metrics(failures))}" if failures else ""
            ),
            "reviewer": "zcode",
            "updated_at": now_iso(),
        })
        data["runs"] = runs
        common.write_json(result_path, data)

        summary.append({
            "image_id": image_id,
            "type": img.get("type", ""),
            "verdict": verdict,
            "colors_used": metrics.get("colors_used", ""),
            "delta_e_p95": metrics.get("delta_e_p95", ""),
            "beads_total": metrics.get("beads_total", ""),
            "total_ms": metrics.get("total_ms", ""),
            "failures": ";".join(merged_test_metrics(failures)),
        })
        print(f"[{n}/{len(images)}] {image_id} {verdict} colors={metrics.get('colors_used','-')} "
              f"p95={metrics.get('delta_e_p95','-')} {metrics.get('total_ms','-')}ms")

    # summary files
    with (out_dir / "summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["image_id", "type", "verdict", "colors_used",
                                          "delta_e_p95", "beads_total", "total_ms", "failures"])
        w.writeheader()
        w.writerows(summary)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    passes = sum(1 for s in summary if s["verdict"] == "pass")
    fails = len(summary) - passes
    types = Counter(s["type"] for s in summary)
    runtimes = [float(s["total_ms"]) for s in summary if s["total_ms"] != ""]
    colors = [int(s["colors_used"]) for s in summary if s["colors_used"] != ""]
    runtime_text = (
        f"{sum(runtimes)/1000:.1f}s 总计，单图 {min(runtimes):.0f}–{max(runtimes):.0f}ms"
        if runtimes else "-"
    )
    colors_text = f"{min(colors)}–{max(colors)}" if colors else "-"

    # batch review
    review_path = common.TESTS / "reviews" / sd / f"{args.batch}.md"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {args.stage} / {args.batch} 冒烟测试总结",
        "",
        f"- 样本：{len(summary)} 张",
        f"- 通过：{passes} / 失败：{fails}",
        f"- 类型分布：{', '.join(f'{k} {v}' for k, v in sorted(types.items()))}",
        f"- 变体：`{variant}`",
        f"- 运行时间：{runtime_text}",
        f"- 使用色数：{colors_text}",
        "",
        "## 验收标准",
        "",
        "1. 20/20 处理完成，无未捕获异常。",
        "2. 网格严格为 29×29，总格数 841。",
        "3. 使用色数 ≤12。",
        "4. 每个色号都存在于 MARD 221。",
        "5. CSV 行数 = 使用色数；格数合计 = 841；豆数 = ceil(格数 × 1.1)。",
        "6. 每张图都有 preview.png / usage.csv / pattern.pdf，且非空。",
        "7. PDF 为 A4、单页、5mm/格、带 10mm 标尺。",
        "8. 记录运行时间；T00 不设性能门槛。",
        "9. **不评价美观**；质量评分在 T01。",
        "",
        "任一结构项不满足 → 该图 `fail`，并写入固定 failure 代码。",
        "",
        "## 失败汇总",
        "",
    ]
    if all_failures:
        for f, c in all_failures.most_common():
            ids = [s["image_id"] for s in summary if f in s["failures"].split(";")]
            lines.append(f"- `{f}` × {c}：{', '.join(ids)}")
    else:
        lines.append("- 无")
    lines += [
        "",
        "## 结论",
        "",
        "T00 只验证结构（跑通、29×29、≤12 色、色号真实存在、PDF/CSV 齐全），**不评价好看与否**。",
        "质量判断在 T01；算法对比在 T02/T03。",
        "",
        "## 产物",
        "",
        f"- 输出目录：`{out_dir.as_posix()}`",
        f"- 汇总：`{(out_dir / 'summary.csv').as_posix()}`",
    ]
    review_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\npass {passes} / fail {fails}")
    print(f"outputs: {out_dir}")
    print(f"review:  {review_path}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
