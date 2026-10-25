#!/usr/bin/env python3
"""Validate the pictile test corpus: naming, paths, hashes, manifests, results."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import common


def check_result(path: Path, image_id: str, image_rel: str, image_hash: str, errors: list[str], warnings: list[str]) -> int:
    try:
        data = common.load_json(path)
    except Exception as exc:
        errors.append(f"{path}: cannot parse JSON: {exc}")
        return 0
    if data.get("image_id") != image_id:
        errors.append(f"{path}: image_id mismatch")
    if data.get("path") != image_rel:
        errors.append(f"{path}: path mismatch")
    if data.get("sha256") != image_hash:
        errors.append(f"{path}: sha256 mismatch")
    runs = data.get("runs")
    if not isinstance(runs, list):
        errors.append(f"{path}: runs must be a list")
        return 0
    for i, run in enumerate(runs):
        where = f"{path}: runs[{i}]"
        for key in ("run_id", "variant", "date", "verdict", "metrics", "failures", "comment", "reviewer"):
            if key not in run:
                errors.append(f"{where}: missing {key}")
        if run.get("verdict") not in common.VERDICTS:
            errors.append(f"{where}: invalid verdict {run.get('verdict')!r}")
        if not isinstance(run.get("metrics"), dict):
            errors.append(f"{where}: metrics must be an object")
        failures = run.get("failures", [])
        if not isinstance(failures, list):
            errors.append(f"{where}: failures must be a list")
        else:
            for f in failures:
                if f not in common.FAILURES:
                    errors.append(f"{where}: unknown failure {f!r}")
    return len(runs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the test corpus.")
    parser.add_argument("--images-root", type=Path, default=None, help="override tests/images location")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    images_root = common.resolve_images_root(args.images_root)
    print(f"images root: {images_root}")
    manifests = list(common.iter_manifests())
    if not manifests:
        print("no manifests yet: tests/manifests is empty")
        return 0

    seen_ids: dict[str, Path] = {}
    expected_images: set[Path] = set()
    expected_results: set[Path] = set()
    run_count = 0
    verdicts = {"pass": 0, "fail": 0, "review": 0, "pending": 0}

    for mp in manifests:
        try:
            data = common.load_json(mp)
        except Exception as exc:
            errors.append(f"{mp}: cannot parse JSON: {exc}")
            continue
        stage = data.get("stage")
        batch = data.get("batch")
        sd = mp.parent.name
        if stage not in common.STAGES:
            errors.append(f"{mp}: unknown stage {stage!r}")
        elif sd != f"{stage}-{common.STAGES[stage]}":
            errors.append(f"{mp}: directory {sd!r} does not match stage {stage!r}")
        if batch != mp.stem:
            errors.append(f"{mp}: batch {batch!r} does not match filename {mp.stem!r}")
        if not common.BATCH_RE.match(str(batch or "")):
            errors.append(f"{mp}: invalid batch {batch!r}")

        for img in data.get("images", []):
            iid = img.get("image_id", "")
            path = img.get("path", "")
            if iid in seen_ids:
                errors.append(f"{iid}: duplicate image_id (also in {seen_ids[iid]})")
            seen_ids[iid] = mp
            m = common.IMAGE_ID_RE.match(iid)
            if not m:
                errors.append(f"{mp}: invalid image_id {iid!r}")
            elif m.group(1) != stage or m.group(2) != batch:
                errors.append(f"{mp}: image_id {iid!r} does not match stage/batch")
            if img.get("type") not in common.TYPES:
                errors.append(f"{iid}: unknown type {img.get('type')!r}")
            if img.get("source_kind") not in common.SOURCE_KINDS:
                errors.append(f"{iid}: unknown source_kind {img.get('source_kind')!r}")
            if "difficulty" in img and not (isinstance(img["difficulty"], int) and 1 <= img["difficulty"] <= 5):
                errors.append(f"{iid}: difficulty must be 1..5")
            image_path = common.resolve_image_path(path, images_root)
            expected_images.add(image_path.resolve())
            if not image_path.exists():
                errors.append(f"{iid}: image missing at {path}")
                continue
            if not common.NAME_RE.match(image_path.name):
                errors.append(f"{iid}: image filename does not match naming convention")
            actual = common.sha256(image_path)
            if actual != img.get("sha256"):
                errors.append(f"{iid}: sha256 mismatch (manifest {img.get('sha256')}, actual {actual})")

            result_path = common.TESTS / "results" / sd / str(batch) / f"{iid}.json"
            expected_results.add(result_path.resolve())
            if not result_path.exists():
                warnings.append(f"{iid}: result JSON missing (pending)")
                verdicts["pending"] += 1
                continue
            n = check_result(result_path, iid, path, img.get("sha256", ""), errors, warnings)
            run_count += n
            if n == 0:
                verdicts["pending"] += 1
            else:
                last = common.load_json(result_path)["runs"][-1]
                verdicts[last.get("verdict", "pending")] += 1

    for p in common.iter_images(images_root):
        if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        if p.resolve() not in expected_images:
            try:
                shown = p.relative_to(images_root).as_posix()
            except ValueError:
                shown = str(p)
            errors.append(f"orphan image (no manifest entry): {shown}")

    for rp in common.iter_results():
        if rp.resolve() not in expected_results:
            errors.append(f"orphan result (no manifest entry): {rp.relative_to(common.ROOT).as_posix()}")

    print(f"manifests: {len(manifests)}  images: {len(seen_ids)}  results: {len(expected_results)}  runs: {run_count}")
    print(f"verdicts: pass={verdicts['pass']} fail={verdicts['fail']} review={verdicts['review']} pending={verdicts['pending']}")
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    if errors:
        print(f"\n{len(errors)} error(s)")
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
