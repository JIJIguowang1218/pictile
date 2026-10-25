"""Shared constants and helpers for pictile test tooling."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
IMAGES_PREFIX = ("tests", "images")

STAGES: Dict[str, str] = {
    "T00": "smoke",
    "T01": "baseline",
    "T02": "bg-removal",
    "T03": "downsample",
    "T04": "palette",
    "T05": "diagnosis",
    "T06": "semantic",
    "T07": "ai-check",
    "T08": "web-usability",
    "T09": "mobile",
}

TYPES = {
    "portrait", "cartoon", "pet", "logo", "text", "product", "scene",
    "abstract", "lowres", "transparent", "multi_subject", "night",
    "texture", "lineart", "screenshot", "hard_negative", "other",
}

SOURCE_KINDS = {"web", "own", "cc0", "generated", "purchased", "other"}

FAILURES = {
    "eye_lost", "text_unreadable", "outline_blur", "island_noise",
    "skin_shift", "banding", "background_clutter", "subject_too_small",
    "thin_line_lost", "color_shift", "detail_lost", "other",
    "pipeline_error", "invalid_color", "grid_mismatch", "cell_count_mismatch",
    "missing_export", "pdf_invalid", "csv_mismatch", "color_count_exceeded",
}

VERDICTS = {"pass", "fail", "review"}

NAME_RE = re.compile(r"^(T[0-9]{2})-(B[0-9]{8}[A-Z])-(I[0-9]{4})\.(jpg|jpeg|png|webp)$")
IMAGE_ID_RE = re.compile(r"^(T[0-9]{2})-(B[0-9]{8}[A-Z])-(I[0-9]{4})$")
BATCH_RE = re.compile(r"^B[0-9]{8}[A-Z]$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_dir(stage: str) -> str:
    if stage not in STAGES:
        raise SystemExit(f"unknown stage {stage!r}; choose from {', '.join(STAGES)}")
    return f"{stage}-{STAGES[stage]}"


def normalize_suffix(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix in {".jpeg", ".jfif"}:
        return ".jpg"
    return suffix


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iter_manifests() -> Iterable[Path]:
    base = TESTS / "manifests"
    if not base.exists():
        return
    for path in sorted(base.rglob("*.json")):
        yield path


def iter_images() -> Iterable[Path]:
    base = TESTS / "images"
    if not base.exists():
        return
    for path in sorted(base.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            yield path


def iter_results() -> Iterable[Path]:
    base = TESTS / "results"
    if not base.exists():
        return
    for path in sorted(base.rglob("*.json")):
        yield path


def image_id_from_path(path: Path) -> str | None:
    m = NAME_RE.match(path.name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def resolve_images_root(override: Path | None = None) -> Path:
    """Where the actual images live on this machine.

    Default: <repo>/tests/images
    Override: tests/local.json -> {"images_root": "E:/pictile-images"}
    """
    if override is not None:
        return override.resolve()
    config = TESTS / "local.json"
    if config.exists():
        data = load_json(config)
        raw = data.get("images_root")
        if raw:
            p = Path(raw)
            return p.resolve() if p.is_absolute() else (ROOT / p).resolve()
    return (TESTS / "images").resolve()


def resolve_image_path(rel_path: str | Path, images_root: Path | None = None) -> Path:
    """Map a canonical manifest path (tests/images/...) to this machine's root."""
    p = Path(rel_path)
    if p.is_absolute():
        return p
    root = resolve_images_root(images_root)
    parts = p.parts
    if len(parts) >= 2 and parts[0] == IMAGES_PREFIX[0] and parts[1] == IMAGES_PREFIX[1]:
        return root.joinpath(*parts[2:])
    return root / p


def iter_images(images_root: Path | None = None) -> Iterable[Path]:
    base = resolve_images_root(images_root)
    if not base.exists():
        return
    for path in sorted(base.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            yield path


def canonical_image_path(stage_dir_name: str, batch: str, filename: str) -> str:
    return (Path("tests") / "images" / stage_dir_name / batch / filename).as_posix()
