#!/usr/bin/env python3
"""Ingest reviewed images from a staging folder into tests/.

Reads 清单.csv, filters 审核状态 == 通过, and calls tests/tools/add_image.py.
The staging file keeps its name; the formal library gets the standard
T??-B????????-I???? naming and the source metadata from the CSV.
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADD_IMAGE = ROOT / "tests" / "tools" / "add_image.py"
DESKTOP = Path.home() / "Desktop"
DEFAULT_STAGING = DESKTOP / "pictile_T00_待审核"
LOG_FIELDS = ["时间", "临时文件名", "image_id", "入库path", "状态", "message"]


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def default_batch() -> str:
    return "B" + datetime.now().strftime("%Y%m%d") + "A"


def find_file(staging: Path, name: str) -> Path | None:
    for p in staging.rglob(name):
        if p.is_file():
            return p
    return None


def source_kind(row: dict) -> str:
    author = (row.get("作者/来源") or "").strip()
    url = (row.get("来源URL") or "").strip()
    if author in {"DiceBear", "scripts/stage_t00.py"} or url.startswith("generated"):
        return "generated"
    return "web"


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest approved staged images.")
    ap.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    ap.add_argument("--manifest", type=Path, default=None, help="default: <staging>/清单.csv")
    ap.add_argument("--stage", default="T00")
    ap.add_argument("--batch", default=None)
    ap.add_argument("--status", default="通过", help="which 审核状态 to ingest")
    ap.add_argument("--images-root", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    staging = args.staging.resolve()
    manifest = (args.manifest or (staging / "清单.csv")).resolve()
    if not manifest.exists():
        raise SystemExit(f"manifest not found: {manifest}")
    batch = args.batch or default_batch()

    with manifest.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    approved = [r for r in rows if (r.get("审核状态") or "").strip() == args.status]
    if not approved:
        print(f"no rows with 审核状态 == {args.status!r}")
        return 0

    log_path = staging / "ingest_log.csv"
    log_exists = log_path.exists()
    log_file = log_path.open("a", encoding="utf-8-sig", newline="")
    logger = csv.DictWriter(log_file, fieldnames=LOG_FIELDS)
    if not log_exists:
        logger.writeheader()

    ok = 0
    failed = 0
    for row in approved:
        temp_name = (row.get("临时文件名") or "").strip()
        rel = (row.get("临时相对路径") or "").strip()
        if rel:
            path = (staging / rel).resolve()
            if not path.is_file():
                path = None
        else:
            path = find_file(staging, temp_name)
        if path is None:
            print(f"MISSING {temp_name}")
            logger.writerow({"时间": now(), "临时文件名": temp_name, "image_id": "", "入库path": "",
                             "状态": "missing", "message": "file not found"})
            failed += 1
            continue

        note = f"staged:{rel or temp_name}"
        remark = (row.get("备注") or "").strip()
        if remark:
            note += f"; {remark}"

        cmd = [
            sys.executable, str(ADD_IMAGE),
            "--stage", args.stage,
            "--batch", batch,
            "--file", str(path),
            "--type", (row.get("入库type") or "other").strip(),
            "--source-kind", source_kind(row),
            "--source-url", (row.get("来源URL") or "").strip(),
            "--license", (row.get("许可") or "unknown").strip(),
            "--note", note,
        ]
        if args.images_root:
            cmd += ["--images-root", str(args.images_root)]

        print("RUN", " ".join(cmd))
        if args.dry_run:
            continue

        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (res.stdout or "") + (res.stderr or "")
        print(out.strip())
        m = re.search(r"image_id:\s*(\S+)", out)
        p = re.search(r"image:\s*(\S+)", out)
        image_id = m.group(1) if m else ""
        image_path = p.group(1) if p else ""
        if res.returncode == 0 and image_id:
            status = "ok"
            ok += 1
        elif "already exists:" in out:
            status = "already"
            ok += 1
        else:
            status = "failed"
            failed += 1
        logger.writerow({"时间": now(), "临时文件名": temp_name, "image_id": image_id,
                         "入库path": image_path, "状态": status, "message": out.strip()[-500:]})
        log_file.flush()

    log_file.close()
    print(f"\napproved: {len(approved)}  ok: {ok}  failed: {failed}")
    if not args.dry_run:
        print(f"log: {log_path}")
        print("next:")
        print("  python tests/tools/validate.py")
        print("  python tests/tools/build_index.py")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
