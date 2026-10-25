#!/usr/bin/env python3
"""Locate the local image folder and check it against the synced manifests.

Typical use after copying tests/images to a USB drive / another machine:

  python tests/tools/locate_images.py --root "E:/pictile-images" --check-hash --write-config

The manifest stores canonical paths like tests/images/T01-baseline/.../I0001.jpg.
This tool maps them to --root and verifies filename + sha256.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import common


def main() -> int:
    parser = argparse.ArgumentParser(description="Locate and verify the local test image folder.")
    parser.add_argument("--root", required=True, type=Path, help="folder that mirrors tests/images")
    parser.add_argument("--check-hash", action="store_true", help="also compare sha256")
    parser.add_argument("--write-config", action="store_true", help="write tests/local.json with this root")
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")

    # If the user pointed at the repo root or tests/, try the images subfolder.
    candidate = root / "tests" / "images"
    if candidate.is_dir() and any(p.name.startswith("T") for p in candidate.iterdir()):
        print(f"note: using {candidate} (found tests/images under --root)")
        root = candidate

    found: dict[str, Path] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        iid = common.image_id_from_path(p)
        if iid:
            found[iid] = p

    expected: dict[str, str] = {}
    for mp in common.iter_manifests():
        data = common.load_json(mp)
        for img in data.get("images", []):
            expected[img["image_id"]] = img.get("sha256", "")

    missing = sorted(set(expected) - set(found))
    extra = sorted(set(found) - set(expected))
    bad_hash = []
    if args.check_hash:
        for iid in sorted(set(expected) & set(found)):
            actual = common.sha256(found[iid])
            if actual != expected[iid]:
                bad_hash.append((iid, str(found[iid])))

    print(f"root: {root}")
    print(f"manifest images: {len(expected)}  found files: {len(found)}")
    if missing:
        print(f"\nMISSING ({len(missing)}):")
        for iid in missing:
            print(f"  {iid}")
    if extra:
        print(f"\nEXTRA files not in manifest ({len(extra)}):")
        for iid in extra:
            print(f"  {iid} -> {found[iid]}")
    if bad_hash:
        print(f"\nSHA256 MISMATCH ({len(bad_hash)}):")
        for iid, p in bad_hash:
            print(f"  {iid} -> {p}")

    if args.write_config:
        common.write_json(common.TESTS / "local.json", {"images_root": str(root)})
        print(f"\nwrote {common.TESTS / 'local.json'}")

    if missing or bad_hash:
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
