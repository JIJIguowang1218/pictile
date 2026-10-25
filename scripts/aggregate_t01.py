#!/usr/bin/env python3
"""Aggregate T01 human ratings, update result verdicts, compute acceptance.

  python scripts/aggregate_t01.py --batch B20261026B
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "tools"))
import common  # noqa: E402

CN_CODES = {
    "眼睛丢了": "eye_lost", "眼睛丢失": "eye_lost", "文字糊": "text_unreadable",
    "轮廓糊": "outline_blur", "噪点": "island_noise", "肤色偏": "skin_shift",
    "色阶断裂": "banding", "背景碎": "background_clutter", "背景杂乱": "background_clutter",
    "主体太小": "subject_too_small", "细线丢失": "thin_line_lost", "偏色": "color_shift",
    "细节丢失": "detail_lost",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_failures(raw: str, warnings: list[str], image_id: str) -> list[str]:
    parts = raw.replace("，", ";").replace(",", ";").split(";")
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        p = CN_CODES.get(p, p)
        if p not in common.FAILURES:
            warnings.append(f"{image_id}: unknown failure tag {p!r}")
            continue
        if p not in out:
            out.append(p)
    return out


def stats(values: list[int]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "pct_ge_3": None}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 3),
        "median": round(statistics.median(values), 3),
        "pct_ge_3": round(sum(1 for v in values if v >= 3) / len(values), 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Aggregate T01 human ratings.")
    ap.add_argument("--batch", required=True)
    ap.add_argument("--rating", type=Path, default=None)
    ap.add_argument("--results-dir", type=Path, default=None)
    ap.add_argument("--review-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    batch = args.batch
    rating_path = (args.rating or (ROOT / "out" / "T01" / batch / "rating.csv")).resolve()
    results_dir = (args.results_dir or (ROOT / "tests" / "results" / "T01-baseline" / batch)).resolve()
    review_dir = (args.review_dir or (ROOT / "tests" / "reviews" / "T01-baseline")).resolve()
    out_dir = (args.out or (ROOT / "out" / "T01" / batch)).resolve()

    if not rating_path.exists():
        raise SystemExit(f"rating CSV not found: {rating_path}")
    rows = list(csv.DictReader(rating_path.open(encoding="utf-8-sig", newline="")))

    warnings: list[str] = []
    invalid: list[tuple[str, str]] = []
    structural = Counter()
    positive, hard, uncategorized = [], [], []
    per_type: dict[str, list[int]] = defaultdict(list)
    hard_failures = Counter()
    rated_rows = 0

    for row in rows:
        iid = (row.get("image_id") or "").strip()
        if not iid:
            continue
        group = (row.get("组别") or "").strip()
        typ = (row.get("类型") or "").strip()
        raw = (row.get("评分") or "").strip()
        if not raw:
            continue
        try:
            rating = int(float(raw))
        except Exception:
            invalid.append((iid, raw))
            continue
        if rating < 1 or rating > 5:
            invalid.append((iid, raw))
            continue
        rated_rows += 1

        result_path = results_dir / f"{iid}.json"
        if not result_path.exists():
            warnings.append(f"{iid}: result JSON missing")
            continue
        data = common.load_json(result_path)
        runs = data.get("runs", [])
        if not runs:
            warnings.append(f"{iid}: no runs in result JSON")
            continue
        run = runs[-1]
        for f in run.get("metrics", {}).get("structural_failures", []):
            structural[f] += 1

        failures = parse_failures(row.get("失败标签") or "", warnings, iid)
        comment = (row.get("评论") or "").strip()
        run["verdict"] = "pass" if rating >= 3 else "fail"
        run["failures"] = failures
        run["comment"] = comment or f"T01 human rating: {rating}/5"
        run["reviewer"] = "owner"
        run["updated_at"] = now_iso()
        run.setdefault("metrics", {})["rating"] = rating
        run["metrics"]["group"] = group
        if not args.dry_run:
            common.write_json(result_path, data)

        if group == "硬负例":
            hard.append(rating)
            for f in failures:
                hard_failures[f] += 1
        elif group == "未分类":
            uncategorized.append(rating)
        else:
            positive.append(rating)
            per_type[typ].append(rating)

    total = len(rows)
    pos_total = sum(1 for r in rows if (r.get("组别") or "").strip() == "正例")
    hard_total = sum(1 for r in rows if (r.get("组别") or "").strip() == "硬负例")
    unc_total = sum(1 for r in rows if (r.get("组别") or "").strip() == "未分类")
    pos_cov = len(positive) / pos_total if pos_total else 0
    hard_cov = len(hard) / hard_total if hard_total else 1.0
    cov = rated_rows / total if total else 0

    ps = stats(positive)
    by_type = {t: stats(v) for t, v in sorted(per_type.items())}
    macro = round(statistics.mean([s["mean"] for s in by_type.values() if s["n"] > 0]), 3) if by_type else None
    bad_categories = {t: s for t, s in by_type.items() if s["n"] >= 3 and s["mean"] is not None and s["mean"] < 2.5}

    reasons = []
    if structural:
        reasons.append(f"structural failures: {dict(structural)}")
    if pos_cov < 1.0:
        reasons.append(f"positive coverage {pos_cov:.0%}")
    if hard_cov < 1.0:
        reasons.append(f"hard-negative coverage {hard_cov:.0%}")
    if ps["n"] == 0:
        reasons.append("no positive ratings")
    else:
        if ps["mean"] < 3.5:
            reasons.append(f"positive mean {ps['mean']} < 3.5")
        if ps["median"] < 3.5:
            reasons.append(f"positive median {ps['median']} < 3.5")
        if ps["pct_ge_3"] < 0.70:
            reasons.append(f"positive >=3 rate {ps['pct_ge_3']:.0%} < 70%")
    if bad_categories:
        reasons.append("category mean <2.5: " + ", ".join(f"{t}={s['mean']}(n={s['n']})" for t, s in bad_categories.items()))
    if invalid:
        reasons.append(f"invalid ratings: {invalid}")

    if cov < 1.0:
        status = "PENDING"
    elif reasons:
        status = "FAIL"
    else:
        status = "PASS"

    summary = {
        "batch": batch,
        "status": status,
        "coverage": {
            "total": total, "rated": rated_rows, "coverage": round(cov, 3),
            "positive": [len(positive), pos_total], "hard_negative": [len(hard), hard_total],
            "uncategorized": [len(uncategorized), unc_total],
        },
        "positive": ps,
        "macro_mean": macro,
        "by_type": by_type,
        "hard_negative": {
            "ratings": hard,
            "mean": round(statistics.mean(hard), 3) if hard else None,
            "failures": dict(hard_failures),
            "note": "not part of the positive average",
        },
        "structural_failures": dict(structural),
        "reasons": reasons,
        "invalid_ratings": invalid,
        "warnings": warnings,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.dry_run:
        (out_dir / "rating_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        lines = [
            f"# T01 / {batch} 人工评分结果",
            "",
            f"- **状态：{status}**",
            f"- 覆盖：{rated_rows}/{total}（{cov:.0%}）",
            f"- 正例：{len(positive)}/{pos_total}，平均 {ps['mean']}，中位数 {ps['median']}，≥3 比例 {ps['pct_ge_3']}",
            f"- 大类均衡平均（macro）：{macro}",
            f"- 硬负例：{len(hard)}/{hard_total}，平均 {summary['hard_negative']['mean']}（不参与正例平均）",
            "",
            "## 正例按类型",
            "",
            "| 类型 | n | 平均 | 中位数 | ≥3 比例 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for t, s in by_type.items():
            lines.append(f"| {t} | {s['n']} | {s['mean']} | {s['median']} | {s['pct_ge_3']} |")
        lines += [
            "",
            "## 未通过原因",
            "",
            "- " + ("无" if not reasons else "\n- ".join(reasons)),
            "",
            "## 硬负例失败标签",
            "",
            "- " + ("无" if not hard_failures else ", ".join(f"{k}×{v}" for k, v in hard_failures.items())),
            "",
            "## 结构问题",
            "",
            "- " + ("无" if not structural else ", ".join(f"{k}×{v}" for k, v in structural.items())),
        ]
        md = "\n".join(lines) + "\n"
        (out_dir / "rating_summary.md").write_text(md, encoding="utf-8")
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / f"{batch}-rating.md").write_text(md, encoding="utf-8")
        print(f"\nwrote {out_dir / 'rating_summary.json'}")
        print(f"wrote {out_dir / 'rating_summary.md'}")
        print(f"wrote {review_dir / (batch + '-rating.md')}")
        print("run python tests/tools/build_index.py to refresh the index")

    return 0 if status == "PASS" else (2 if status == "PENDING" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
