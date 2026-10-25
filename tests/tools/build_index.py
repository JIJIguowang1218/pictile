#!/usr/bin/env python3
"""Build tests/index.csv and tests/index.md from manifests and results."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import common


def latest_run(result_path: Path) -> dict | None:
    if not result_path.exists():
        return None
    try:
        data = common.load_json(result_path)
    except Exception:
        return None
    runs = data.get("runs") or []
    return runs[-1] if runs else None


def md_escape(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def main() -> None:
    rows = []
    for mp in common.iter_manifests():
        data = common.load_json(mp)
        stage = data.get("stage", "")
        batch = data.get("batch", "")
        sd = mp.parent.name
        for img in data.get("images", []):
            iid = img.get("image_id", "")
            result_path = common.TESTS / "results" / sd / batch / f"{iid}.json"
            run = latest_run(result_path)
            rows.append(
                {
                    "image_id": iid,
                    "stage": stage,
                    "batch": batch,
                    "type": img.get("type", ""),
                    "source_kind": img.get("source_kind", ""),
                    "license": img.get("license", ""),
                    "verdict": (run or {}).get("verdict", "pending"),
                    "failures": ";".join((run or {}).get("failures", [])),
                    "comment": (run or {}).get("comment", ""),
                    "reviewer": (run or {}).get("reviewer", ""),
                    "run_id": (run or {}).get("run_id", ""),
                    "variant": (run or {}).get("variant", ""),
                    "path": img.get("path", ""),
                }
            )

    rows.sort(key=lambda r: r["image_id"])

    csv_path = common.TESTS / "index.csv"
    fields = ["image_id", "stage", "batch", "type", "source_kind", "license", "verdict",
              "failures", "comment", "reviewer", "run_id", "variant", "path"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    stage_stats: dict[str, Counter] = defaultdict(Counter)
    type_stats: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        stage_stats[r["stage"]][r["verdict"]] += 1
        stage_stats[r["stage"]]["total"] += 1
        type_stats[r["type"]][r["verdict"]] += 1
        type_stats[r["type"]]["total"] += 1

    lines = [
        "# 测试索引（自动生成，勿手改）",
        "",
        f"总图片：{len(rows)}",
        "",
        "## 按阶段",
        "",
        "| 阶段 | 总数 | pass | fail | review | pending |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for stage in sorted(stage_stats):
        s = stage_stats[stage]
        lines.append(f"| {stage} | {s['total']} | {s['pass']} | {s['fail']} | {s['review']} | {s['pending']} |")

    lines += [
        "",
        "## 按类型",
        "",
        "| 类型 | 总数 | pass | fail | review | pending |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for t in sorted(type_stats):
        s = type_stats[t]
        lines.append(f"| {t} | {s['total']} | {s['pass']} | {s['fail']} | {s['review']} | {s['pending']} |")

    lines += [
        "",
        "## 明细",
        "",
        "| image_id | type | verdict | failures | comment | variant | path |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {md_escape(r['image_id'])} | {md_escape(r['type'])} | {md_escape(r['verdict'])} | "
            f"{md_escape(r['failures'])} | {md_escape(r['comment'])} | {md_escape(r['variant'])} | "
            f"{md_escape(r['path'])} |"
        )

    md_path = common.TESTS / "index.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {csv_path.relative_to(common.ROOT).as_posix()}")
    print(f"wrote {md_path.relative_to(common.ROOT).as_posix()}")
    print(f"rows: {len(rows)}")


if __name__ == "__main__":
    main()
