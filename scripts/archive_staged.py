#!/usr/bin/env python3
"""Move reviewed staging contents into tests/archive (a move, never a delete).

The desktop staging folder must be left empty after a batch is ingested. This
script moves everything out of it into the project archive, preserving the
original files and the review metadata. It refuses to overwrite a non-empty
archive.

  python scripts/archive_staged.py --stage T00 --batch B20261026A \
      --staging "C:/Users/86136/Desktop/pictile_T00_待审核"
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = {
    "T00": "smoke", "T01": "baseline", "T02": "bg-removal", "T03": "downsample",
    "T04": "palette", "T05": "diagnosis", "T06": "semantic", "T07": "ai-check",
    "T08": "web-usability", "T09": "mobile",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Move staging contents into tests/archive.")
    ap.add_argument("--staging", type=Path, required=True)
    ap.add_argument("--stage", choices=sorted(STAGES), required=True)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--dest", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    staging = args.staging.resolve()
    if not staging.is_dir():
        raise SystemExit(f"not a directory: {staging}")
    items = sorted(staging.iterdir())
    if not items:
        print("staging is already empty")
        return 0

    dest = (args.dest or (ROOT / "tests" / "archive" / f"{args.stage}-{STAGES[args.stage]}" / args.batch)).resolve()
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"archive not empty: {dest}")
    if dest == staging:
        raise SystemExit("destination must differ from staging")

    print(f"staging: {staging}")
    print(f"archive: {dest}")
    print(f"items: {len(items)}")
    for item in items:
        target = dest / item.name
        if target.exists():
            raise SystemExit(f"target exists: {target}")
        print(f"  {'MOVE' if not args.dry_run else 'DRY '} {item.name}")
        if not args.dry_run:
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(target))

    if args.dry_run:
        print("dry-run: nothing moved")
    else:
        print(f"\nmoved {len(items)} item(s); staging is now empty")
    return 0


if __name__ == "__main__":
    sys.exit(main())
