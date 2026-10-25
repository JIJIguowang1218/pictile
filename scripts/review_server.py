#!/usr/bin/env python3
"""Local review server for pictile test batches.

Start:
  python scripts/review_server.py --stage T01 --batch B20261026B --open

The frontend is scripts/review_ui.html. Acceptance text and score rubric live in
out/<stage>/<batch>/review_config.json (auto-copied from scripts/review_configs/).
Confirming a review writes:
  out/<stage>/<batch>/review/<image_id>.json
  out/<stage>/<batch>/rating.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT / "tests" / "tools"))
import common  # noqa: E402

MAX_BODY = 1_000_000
DEFAULT_RATING_COLUMNS = {"score": "评分", "tags": "失败标签", "notes": "评论"}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def atomic_write_json(path: Path, data) -> None:
    atomic_write_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_usage(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                rows.append({
                    "code": row.get("code", ""),
                    "hex": row.get("hex", ""),
                    "cells": int(row.get("cells", 0)),
                    "beads": int(row.get("beads_incl_10pct", 0)),
                })
            except Exception:
                continue
    return rows


def group_of(img_type: str) -> tuple[str, str]:
    if img_type == "hard_negative":
        return "硬负例", "hard_negative"
    if img_type == "other":
        return "未分类", "uncategorized"
    return "正例", "positive"


def review_from_rating(row: dict | None, cols: dict) -> dict | None:
    if not row:
        return None
    raw = (row.get(cols["score"]) or "").strip()
    if not raw:
        return None
    try:
        score = int(float(raw))
    except Exception:
        return None
    if not (1 <= score <= 5):
        return None
    tags = [x.strip() for x in (row.get(cols["tags"]) or "").replace("，", ";").split(";") if x.strip()]
    return {
        "score": score,
        "notes": (row.get(cols["notes"]) or "").strip(),
        "failure_tags": tags,
        "updated_at": "",
        "source": "rating.csv",
    }


def build_state(stage: str, batch: str, out_override: Path | None) -> dict:
    sd = common.stage_dir(stage)
    manifest_path = common.TESTS / "manifests" / sd / f"{batch}.json"
    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")
    manifest = read_json(manifest_path)
    results_dir = common.TESTS / "results" / sd / batch
    out_dir = (out_override or (ROOT / "out" / stage / batch)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    review_dir = out_dir / "review"
    rating_path = out_dir / "rating.csv"

    config_path = out_dir / "review_config.json"
    template = SCRIPTS / "review_configs" / f"{stage}.json"
    if not config_path.exists():
        if template.exists():
            shutil.copy2(template, config_path)
        else:
            atomic_write_json(config_path, {
                "title": f"{stage} review",
                "acceptance": {"headline": "验收标准", "sections": []},
                "score_labels": {str(i): f"{i} 分" for i in range(1, 6)},
                "failure_tags": sorted(common.FAILURES),
            })
    config = read_json(config_path)
    rating_cols = {**DEFAULT_RATING_COLUMNS, **config.get("rating_columns", {})}

    rating_map = {}
    if rating_path.exists():
        with rating_path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("image_id"):
                    rating_map[row["image_id"]] = row

    images_root = common.resolve_images_root()
    images = []
    server_files: dict[str, dict] = {}

    for img in manifest.get("images", []):
        image_id = img["image_id"]
        typ = img.get("type", "")
        group, group_key = group_of(typ)

        result_path = results_dir / f"{image_id}.json"
        metrics: dict = {}
        if result_path.exists():
            try:
                data = read_json(result_path)
                runs = data.get("runs") or []
                if runs:
                    metrics = runs[-1].get("metrics") or {}
            except Exception:
                pass
        meta_path = out_dir / image_id / "meta.json"
        if meta_path.exists():
            try:
                meta = read_json(meta_path)
                metrics = {**(meta.get("metrics") or {}), **metrics}
            except Exception:
                pass

        orig_size = None
        try:
            orig_size = metrics.get("image_meta", {}).get("orig_size")
        except Exception:
            pass

        live_path = review_dir / f"{image_id}.json"
        review = None
        if live_path.exists():
            try:
                review = read_json(live_path)
                review["source"] = "review.json"
            except Exception:
                review = None
        if review is None:
            review = review_from_rating(rating_map.get(image_id), rating_cols)

        preview_path = out_dir / image_id / "preview.png"
        pdf_path = out_dir / image_id / "pattern.pdf"
        csv_path = out_dir / image_id / "usage.csv"
        original_path = common.resolve_image_path(img["path"], images_root)
        server_files[image_id] = {
            "original": original_path,
            "preview": preview_path,
            "pdf": pdf_path,
            "csv": csv_path,
        }

        images.append({
            "image_id": image_id,
            "type": typ,
            "group": group,
            "group_key": group_key,
            "orig_size": orig_size,
            "metrics": {
                "grid": metrics.get("grid"),
                "colors_used": metrics.get("colors_used"),
                "beads_total": metrics.get("beads_total"),
                "delta_e_p95": metrics.get("delta_e_p95"),
                "total_ms": metrics.get("total_ms"),
                "palette": metrics.get("palette"),
                "structural_failures": metrics.get("structural_failures", []),
            },
            "colors": read_usage(csv_path),
            "review": review,
            "original_url": f"/api/image/{image_id}/original",
            "preview_url": f"/api/image/{image_id}/preview",
            "pdf_url": f"/api/image/{image_id}/pdf",
            "csv_url": f"/api/image/{image_id}/csv",
        })

    try:
        config_rel = config_path.relative_to(ROOT).as_posix()
    except ValueError:
        config_rel = str(config_path)

    api_config = {
        "stage": stage,
        "batch": batch,
        "title": config.get("title", f"{stage} review"),
        "acceptance": config.get("acceptance", {}),
        "score_labels": config.get("score_labels", {}),
        "failure_tags": config.get("failure_tags", sorted(common.FAILURES)),
        "rating_columns": rating_cols,
        "config_rel": config_rel,
        "images": images,
        "progress": progress(images),
    }
    return {
        "api_config": api_config,
        "server_files": server_files,
        "images": images,
        "out_dir": out_dir,
        "review_dir": review_dir,
        "rating_path": rating_path,
        "config": config,
        "config_path": config_path,
        "rating_cols": rating_cols,
    }


def progress(images: list[dict]) -> dict:
    total = len(images)
    reviewed = sum(1 for i in images if i.get("review"))
    by_group = {}
    for i in images:
        g = i.get("group", "")
        by_group.setdefault(g, [0, 0])
        by_group[g][1] += 1
        if i.get("review"):
            by_group[g][0] += 1
    return {"total": total, "reviewed": reviewed, "remaining": total - reviewed, "by_group": by_group}


def save_review(state: dict, payload: dict) -> dict:
    image_id = (payload.get("image_id") or "").strip()
    if not common.IMAGE_ID_RE.match(image_id):
        raise ValueError("invalid image_id")
    entry = next((i for i in state["images"] if i["image_id"] == image_id), None)
    if entry is None:
        raise ValueError("unknown image_id")

    try:
        score = int(payload.get("score"))
    except Exception:
        raise ValueError("score must be 1-5")
    if score < 1 or score > 5:
        raise ValueError("score must be 1-5")

    notes = (payload.get("notes") or "").strip()
    if len(notes) > 5000:
        raise ValueError("notes too long (max 5000)")

    allowed = set(state["api_config"].get("failure_tags") or [])
    tags = payload.get("failure_tags") or []
    if not isinstance(tags, list):
        raise ValueError("failure_tags must be a list")
    tags = [str(t).strip() for t in tags if str(t).strip()]
    bad = [t for t in tags if t not in allowed]
    if bad:
        raise ValueError(f"unknown failure tags: {bad}")

    review = {
        "image_id": image_id,
        "score": score,
        "notes": notes,
        "failure_tags": tags,
        "reviewer": payload.get("reviewer") or "owner",
        "updated_at": now_iso(),
    }
    state["review_dir"].mkdir(parents=True, exist_ok=True)
    atomic_write_json(state["review_dir"] / f"{image_id}.json", review)

    cols = state["rating_cols"]
    rating_path = state["rating_path"]
    rows = []
    fields = ["image_id", "组别", "类型", cols["score"], cols["tags"], cols["notes"], "预览", "PDF", "CSV"]
    if rating_path.exists():
        with rating_path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or fields
            rows = list(reader)

    found = False
    for row in rows:
        if row.get("image_id") == image_id:
            row[cols["score"]] = str(score)
            row[cols["tags"]] = ";".join(tags)
            row[cols["notes"]] = notes
            found = True
            break
    if not found:
        row = {k: "" for k in fields}
        row["image_id"] = image_id
        row["组别"] = entry.get("group", "")
        row["类型"] = entry.get("type", "")
        row[cols["score"]] = str(score)
        row[cols["tags"]] = ";".join(tags)
        row[cols["notes"]] = notes
        rows.append(row)

    tmp = rating_path.with_name(rating_path.name + ".tmp")
    rating_path.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, restval="")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, rating_path)

    entry["review"] = {k: review[k] for k in ("score", "notes", "failure_tags")}
    state["api_config"]["progress"] = progress(state["images"])
    return {"ok": True, "progress": state["api_config"]["progress"], "review": review}


class Handler(BaseHTTPRequestHandler):
    server_version = "pictile-review/0.1"

    @property
    def state(self) -> dict:
        return self.server.app_state  # type: ignore[attr-defined]

    def send_json(self, obj, code: int = 200) -> None:
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, code: int, message: str) -> None:
        self.send_json({"error": message}, code)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = (SCRIPTS / "review_ui.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html)
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path == "/api/config":
            self.send_json(self.state["api_config"])
            return
        m = re.match(r"^/api/image/([^/]+)/(original|preview|pdf|csv)$", path)
        if m:
            image_id, kind = m.group(1), m.group(2)
            files = self.state["server_files"].get(image_id)
            if not files:
                self.send_error_json(404, "unknown image")
                return
            file_path: Path = files[kind]
            if not file_path.exists():
                self.send_error_json(404, f"{kind} not found")
                return
            data = file_path.read_bytes()
            if kind == "pdf":
                ctype = "application/pdf"
            elif kind == "csv":
                ctype = "text/csv; charset=utf-8"
            elif kind == "preview":
                ctype = "image/png"
            else:
                ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        m = re.match(r"^/api/review/([^/]+)$", path)
        if m:
            image_id = m.group(1)
            review_path = self.state["review_dir"] / f"{image_id}.json"
            if not review_path.exists():
                self.send_error_json(404, "not reviewed")
                return
            self.send_json(read_json(review_path))
            return
        self.send_error_json(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/api/review":
            self.send_error_json(404, "not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self.send_error_json(413, "invalid body size")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            result = save_review(self.state, payload)
            self.send_json(result)
        except ValueError as exc:
            self.send_error_json(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.send_error_json(500, f"{type(exc).__name__}: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Local pictile review server.")
    ap.add_argument("--stage", default="T01")
    ap.add_argument("--batch", required=True)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--out-dir", type=Path, default=None, help="override out/<stage>/<batch>")
    ap.add_argument("--open", action="store_true", help="open the browser")
    args = ap.parse_args()

    state = build_state(args.stage, args.batch, args.out_dir)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.app_state = state  # type: ignore[attr-defined]

    url = f"http://{args.host}:{args.port}/"
    print(f"pictile review: {url}")
    print(f"batch: {args.stage} / {args.batch}")
    print(f"out:   {state['out_dir']}")
    print(f"config:{state['config_path']}")
    print("Ctrl+C to stop")
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
