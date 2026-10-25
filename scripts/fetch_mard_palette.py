#!/usr/bin/env python3
"""Fetch MARD 221 / 291 palette data from beadsheet's generated palettes bundle.

The bundle attributes the MARD values to makebead/craft-color-codes (CC BY 4.0),
reconciled from several public community datasets. Values are approximate screen
values, not spectrometer measurements. See src/pictile/data/README.md.
"""
from __future__ import annotations

import csv
import re
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) pictile-palette/0.1"
BASE = "https://beadsheet.com"
OUT = Path(__file__).resolve().parents[1] / "src" / "pictile" / "data"
COLOR_RE = re.compile(r'\{"code":"([^"]+)","name":"([^"]*)","hex":"(#[0-9A-Fa-f]{6})"')


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8")


def extract_object(js: str, key: str) -> str:
    marker = f'"{key}":'
    i = js.find(marker)
    if i < 0:
        raise SystemExit(f"{key} not found in bundle")
    start = js.find("{", i)
    depth = 0
    in_str = False
    esc = False
    for j in range(start, len(js)):
        ch = js[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return js[start:j + 1]
    raise SystemExit(f"unbalanced object for {key}")


def parse_colors(obj: str) -> list[tuple[str, str, str]]:
    colors = COLOR_RE.findall(obj)
    seen = set()
    out = []
    for code, name, hexv in colors:
        if code in seen:
            continue
        seen.add(code)
        out.append((code, name, hexv.upper()))
    return out


def main() -> None:
    home = get(BASE + "/")
    app_m = re.search(r'/assets/app\.[a-f0-9]+\.js', home)
    if not app_m:
        raise SystemExit("app bundle not found")
    app_js = get(BASE + app_m.group(0))
    pal_m = re.search(r'\./palettes\.[a-f0-9]+\.js', app_js)
    if not pal_m:
        raise SystemExit("palettes bundle not found")
    pal_url = BASE + "/assets/" + pal_m.group(0)[2:]
    print("palettes:", pal_url)
    js = get(pal_url)

    OUT.mkdir(parents=True, exist_ok=True)
    for key, expected in [("mard221", 221), ("mard291", 291)]:
        colors = parse_colors(extract_object(js, key))
        print(key, len(colors))
        if len(colors) != expected:
            raise SystemExit(f"{key}: expected {expected}, got {len(colors)}")
        path = OUT / f"{key}.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["code", "name", "hex"])
            w.writerows(colors)
        print("wrote", path)

    readme = OUT / "README.md"
    readme.write_text(
        "# 色板数据\n\n"
        "## MARD 221 / 291\n\n"
        "- 文件：`mard221.csv`（A–H + M 系列）、`mard291.csv`（全色）。\n"
        "- 来源：[beadsheet.com](https://beadsheet.com/) 的 `palettes.js`；其注释标明 MARD 数据来自 "
        "[makebead/craft-color-codes](https://github.com/makebead/craft-color-codes) 的 "
        "`data/csv/mard-291.csv`，许可 **CC BY 4.0**。\n"
        "- 性质：社区整理、屏幕近似值，**不是分光仪实测 LAB**。批次、光线、屏幕差异都会影响观感。\n"
        "- 用途：v1 的近似色板；落地前必须用实测色值覆盖，并保留版本与来源。\n"
        "- 抓取脚本：`scripts/fetch_mard_palette.py`。\n",
        encoding="utf-8",
    )
    print("wrote", readme)


if __name__ == "__main__":
    main()
