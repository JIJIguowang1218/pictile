#!/usr/bin/env python3
"""Add an image to the pictile test corpus.

Example:
  python tests/tools/add_image.py --stage T01 --file "C:/img.jpg" \
      --type cartoon --source-kind web --source-url "https://..." \
      --license unknown --difficulty 3 --note "用户找的网图，仅内部测试"
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import common

try:
    from PIL import Image  # type: ignore
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def default_batch() -> str:
    return "B" + datetime.now().strftime("%Y%m%d") + "A"


def load_manifest(path: Path, stage: str, batch: str) -> dict:
    if path.exists():
        data = common.load_json(path)
        if data.get("stage") != stage or data.get("batch") != batch:
            raise SystemExit(f"manifest mismatch: {path}")
        return data
    return {
        "stage": stage,
        "stage_name": common.STAGES[stage],
        "batch": batch,
        "created_at": now_iso(),
        "images": [],
    }


def next_code(manifest: dict) -> str:
    used = set()
    for img in manifest["images"]:
        m = re.search(r"I([0-9]{4})$", img["image_id"])
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    if n > 9999:
        raise SystemExit("batch image code exhausted (max 9999)")
    return f"I{n:04d}"


def has_alpha(path: Path) -> bool:
    if not HAS_PIL:
        return False
    try:
        with Image.open(path) as im:
            return "A" in im.getbands() or (im.mode == "P" and "transparency" in im.info)
    except Exception:
        return False


def choose_ext(src: Path) -> str:
    suffix = common.normalize_suffix(src.suffix)
    if not HAS_PIL:
        return suffix
    if suffix in {".png", ".webp"} and has_alpha(src):
        return ".png"
    return ".jpg"


def write_image(src: Path, dst: Path, ext: str, normalize: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not normalize:
        if common.normalize_suffix(src.suffix) != ext:
            raise SystemExit("cannot keep source format when extension changes; drop --no-normalize")
        shutil.copy2(src, dst)
        return
    if not HAS_PIL:
        print("warning: Pillow not installed; copied original without normalization", file=sys.stderr)
        shutil.copy2(src, dst)
        return
    with Image.open(src) as im:
        im.load()
        if ext == ".png":
            if im.mode not in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
            im.thumbnail((1600, 1600), Image.LANCZOS)
            im.save(dst, format="PNG", optimize=True)
        else:
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGB")
            im.thumbnail((1600, 1600), Image.LANCZOS)
            im.save(dst, format="JPEG", quality=90, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Add an image to tests/images and its manifest.")
    parser.add_argument("--stage", required=True, choices=sorted(common.STAGES))
    parser.add_argument("--batch", default=None, help="default: B{YYYYMMDD}A")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--type", required=True, choices=sorted(common.TYPES))
    parser.add_argument("--source-kind", default="web", choices=sorted(common.SOURCE_KINDS))
    parser.add_argument("--source-url", default="")
    parser.add_argument("--license", default="unknown")
    parser.add_argument("--difficulty", type=int, choices=range(1, 6))
    parser.add_argument("--note", default="")
    parser.add_argument("--images-root", type=Path, default=None, help="override tests/images location")
    parser.add_argument("--no-normalize", action="store_true", help="copy as-is (must keep extension)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    src = args.file.resolve()
    if not src.is_file():
        raise SystemExit(f"file not found: {src}")

    batch = args.batch or default_batch()
    if not common.BATCH_RE.match(batch):
        raise SystemExit(f"invalid batch {batch!r}; expected BYYYYMMDD + A-Z")

    sd = common.stage_dir(args.stage)
    manifest_path = common.TESTS / "manifests" / sd / f"{batch}.json"
    manifest = load_manifest(manifest_path, args.stage, batch)

    src_hash = common.sha256(src)
    for img in manifest["images"]:
        if img.get("sha256") == src_hash:
            print(f"already exists: {img['image_id']} -> {img['path']}")
            return

    code = next_code(manifest)
    image_id = f"{args.stage}-{batch}-{code}"
    ext = common.normalize_suffix(src.suffix) if args.no_normalize else choose_ext(src)
    filename = f"{image_id}{ext}"
    image_rel = common.canonical_image_path(sd, batch, filename)
    result_rel = Path("tests") / "results" / sd / batch / f"{image_id}.json"
    images_root = common.resolve_images_root(args.images_root)
    image_path = common.resolve_image_path(image_rel, images_root)
    result_path = common.ROOT / result_rel

    print(f"image_id: {image_id}")
    print(f"images_root: {images_root}")
    print(f"image:    {image_rel}")
    print(f"result:   {result_rel.as_posix()}")

    if args.dry_run:
        print("dry-run: nothing written")
        return

    write_image(src, image_path, ext, normalize=not args.no_normalize)
    stored_hash = common.sha256(image_path)

    entry = {
        "image_id": image_id,
        "path": image_rel,
        "sha256": stored_hash,
        "type": args.type,
        "source_kind": args.source_kind,
        "source_url": args.source_url,
        "license": args.license,
        "notes": args.note,
        "added_at": now_iso(),
    }
    if args.difficulty is not None:
        entry["difficulty"] = args.difficulty

    manifest["images"].append(entry)
    common.write_json(manifest_path, manifest)
    common.write_json(
        result_path,
        {"image_id": image_id, "path": image_rel, "sha256": stored_hash, "runs": []},
    )

    print("added.")
    print("next: run the test, append a run to the result JSON, then run:")
    print("  python tests/tools/validate.py")
    print("  python tests/tools/build_index.py")


if __name__ == "__main__":
    main()
