#!/usr/bin/env python3
"""Stage 20 T00 smoke-test images on the Desktop for human review.

This does NOT touch tests/. After review, run scripts/ingest_staged.py.

Sources: Picsum (Unsplash photos), PlaceDog, RandomUser, DiceBear, and locally
generated text/UI images. Every downloaded file records its source URL and license
in 清单.csv; synthetic files are marked as self-generated (CC0).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) pictile-staging/0.1"
PICSUM_LIST = "https://picsum.photos/v2/list?page=1&limit=100"
DESKTOP = Path.home() / "Desktop"
DEFAULT_OUT = DESKTOP / "pictile_T00_待审核"

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
]


def font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        data = r.read()
    dst.write_bytes(data)


def picsum_meta() -> dict[str, dict]:
    try:
        req = urllib.request.Request(PICSUM_LIST, headers={"User-Agent": UA})
        import json
        with urllib.request.urlopen(req, timeout=40) as r:
            data = json.loads(r.read().decode("utf-8"))
        return {str(x["id"]): x for x in data}
    except Exception as exc:
        print(f"warning: Picsum metadata failed: {exc}")
        return {}


def synthetic_text(path: Path) -> None:
    W = H = 1200
    im = Image.new("RGB", (W, H), (247, 243, 235))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 28], fill=(35, 45, 60))
    d.rectangle([0, H - 40, W, H], fill=(35, 45, 60))
    for i, color in enumerate([(230, 120, 80), (80, 160, 140), (240, 200, 90)]):
        d.ellipse([90 + i * 150, 170, 170 + i * 150, 250], fill=color)
    d.text((90, 330), "拼豆图纸", font=font(170), fill=(30, 30, 30))
    d.text((100, 560), "PICTILE / T00", font=font(54), fill=(120, 110, 100))
    d.text((100, 650), "把一张图变成能照着拼的图纸", font=font(46), fill=(80, 80, 80))
    d.rounded_rectangle([100, 780, 1100, 1000], radius=24, outline=(40, 40, 40), width=6)
    d.text((140, 820), "色号 A1  A2  A3  B1  B2", font=font(44), fill=(40, 40, 40))
    d.text((140, 890), "29 × 29  ·  12 色  ·  MARD 221", font=font(38), fill=(90, 90, 90))
    im.save(path, format="PNG", optimize=True)


def synthetic_ui(path: Path) -> None:
    W, H = 1200, 800
    im = Image.new("RGB", (W, H), (245, 247, 250))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 70], fill=(35, 45, 60))
    d.text((28, 18), "拼豆图纸生成器", font=font(36), fill=(255, 255, 255))
    d.rectangle([0, 70, 250, H], fill=(232, 236, 242))
    for i, label in enumerate(["上传图片", "尺寸", "色板", "导出"]):
        d.rounded_rectangle([20, 110 + i * 70, 230, 165 + i * 70], radius=10, fill=(255, 255, 255))
        d.text((42, 122 + i * 70), label, font=font(28), fill=(40, 40, 40))
    d.rounded_rectangle([290, 110, 1160, 420], radius=14, fill=(255, 255, 255), outline=(210, 215, 225), width=2)
    d.text((320, 135), "预览", font=font(30), fill=(40, 40, 40))
    for r in range(8):
        for c in range(8):
            color = (200, 80, 80) if (r + c) % 3 == 0 else (80, 150, 200) if r % 2 else (240, 200, 90)
            d.rectangle([340 + c * 46, 190 + r * 26, 380 + c * 46, 210 + r * 26], fill=color)
    d.rounded_rectangle([290, 450, 1160, 740], radius=14, fill=(255, 255, 255), outline=(210, 215, 225), width=2)
    d.text((320, 480), "诊断", font=font(30), fill=(40, 40, 40))
    for i, line in enumerate(["左眼和背景混在一起，五官不可辨", "建议：加一圈深色描边（1 颗豆宽）", "代价：+1 色、+12 颗豆、+2 分钟"]):
        d.text((320, 540 + i * 52), line, font=font(30), fill=(70, 70, 70))
    d.rounded_rectangle([880, 660, 1120, 715], radius=10, fill=(60, 140, 220))
    d.text((920, 670), "一键修复", font=font(30), fill=(255, 255, 255))
    im.save(path, format="PNG", optimize=True)


def contact_sheet(items: list[dict], out: Path) -> None:
    cell, label_h, cols = 300, 44, 5
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    f = font(22)
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        x, y = c * cell, r * (cell + label_h)
        im = Image.open(it["path"]).convert("RGBA")
        bg = Image.new("RGBA", (cell, cell), (255, 255, 255, 255))
        im.thumbnail((cell - 12, cell - 12), Image.LANCZOS)
        bg.alpha_composite(im, ((cell - im.width) // 2, (cell - im.height) // 2))
        sheet.paste(bg.convert("RGB"), (x, y))
        label = f'{it["num"]} {it["short"]}'
        d.text((x + 8, y + cell + 10), label, font=f, fill=(20, 20, 20))
    sheet.save(out, quality=88)


def write_manifest(items: list[dict], out: Path) -> None:
    fields = ["编号", "临时文件名", "中文类型", "入库type", "说明", "来源URL", "下载URL",
              "作者/来源", "许可", "原始尺寸", "sha256", "审核状态", "备注"]
    with (out / "清单.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for it in items:
            w.writerow({
                "编号": it["num"],
                "临时文件名": it["path"].name,
                "中文类型": it["chinese_type"],
                "入库type": it["final_type"],
                "说明": it["desc"],
                "来源URL": it["source_url"],
                "下载URL": it["download_url"],
                "作者/来源": it["author"],
                "许可": it["license"],
                "原始尺寸": it["size"],
                "sha256": it["sha256"],
                "审核状态": "待审",
                "备注": it["note"],
            })


def write_review(items: list[dict], out: Path) -> None:
    lines = [
        "# T00 待审核清单",
        "",
        "先打开 `T00_总览.jpg` 看整体，再逐张决定。",
        "",
        "在 `清单.csv` 的 **审核状态** 列填：`通过` / `拒绝` / `替换`；在 **备注** 写原因。",
        "",
        "| 编号 | 文件 | 中文类型 | 入库 type | 来源 | 许可 | 审核状态 | 备注 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for it in items:
        lines.append(
            f'| {it["num"]} | {it["path"].name} | {it["chinese_type"]} | {it["final_type"]} | '
            f'{it["author"]} | {it["license"]} | 待审 | {it["note"]} |'
        )
    lines += [
        "",
        "## T00 在测什么",
        "",
        "只测结构：能跑通、不崩溃、29×29、≤12 色、色号都在 MARD 221、PDF/CSV 齐全。",
        "不测好看不好看，那是 T01。",
        "",
        "## 审核通过后",
        "",
        "```bash",
        'python scripts/ingest_staged.py --staging "C:/Users/86136/Desktop/pictile_T00_待审核"',
        "```",
    ]
    (out / "审查表.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(out: Path) -> None:
    text = f"""# pictile T00 待审核图片

这是**临时暂存区**，不是测试库。审核通过后才会通过 `scripts/ingest_staged.py` 进入 `tests/`。

## 怎么审

1. 打开 `T00_总览.jpg` 看 20 张整体。
2. 打开 `清单.csv`（Excel 可直接编辑），在 `审核状态` 填 `通过` / `拒绝` / `替换`。
3. 需要说明的写在 `备注`。
4. 拒绝/替换的图，我会补新的；通过的后再正式入库。

## 类型与数量

- 卡通 3、人物 3、宠物 2、Logo 3、产品/场景 2、文字/截图 2、硬负例 3、简单正例 2 = 20

## 注意

- 这些图只用于内部测试；来源、许可、哈希都记录在 `清单.csv`。
- 不需要改文件名；正式入库时才按 `T00-B...-I....` 规范命名。
- 图片放在桌面，不进 Git。
"""
    (out / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for folder in [
        "01_卡通", "02_人物", "03_宠物", "04_Logo", "05_产品食物风景",
        "06_文字截图地图", "07_硬负例抽象", "08_简单正例",
    ]:
        (out / folder).mkdir(exist_ok=True)

    meta = picsum_meta()

    # num, folder, chinese_type, final_type, short, desc, kind, ref
    specs = [
        ("01", "01_卡通", "卡通", "cartoon", "卡通", "冒险者头像", "dicebear",
         "https://api.dicebear.com/9.x/adventurer/png?seed=pictile-cartoon-1"),
        ("02", "01_卡通", "卡通", "cartoon", "卡通", "机器人角色", "dicebear",
         "https://api.dicebear.com/9.x/bottts/png?seed=pictile-cartoon-2"),
        ("03", "01_卡通", "卡通", "cartoon", "卡通", "表情角色", "dicebear",
         "https://api.dicebear.com/9.x/fun-emoji/png?seed=pictile-cartoon-3"),
        ("04", "02_人物", "人物", "portrait", "人物", "正面肖像_女", "web",
         "https://randomuser.me/api/portraits/women/44.jpg"),
        ("05", "02_人物", "人物", "portrait", "人物", "正面肖像_男", "web",
         "https://randomuser.me/api/portraits/men/32.jpg"),
        ("06", "02_人物", "人物", "portrait", "人物", "工作场景", "picsum", "1"),
        ("07", "03_宠物", "宠物", "pet", "宠物", "狗狗正面", "web",
         "https://placedog.net/1200/1200?id=1"),
        ("08", "03_宠物", "宠物", "pet", "宠物", "狗狗侧面", "web",
         "https://placedog.net/1200/1200?id=10"),
        ("09", "04_Logo", "Logo", "logo", "Logo", "字母标志", "dicebear",
         "https://api.dicebear.com/9.x/initials/png?seed=PT"),
        ("10", "04_Logo", "Logo", "logo", "Logo", "几何形状", "dicebear",
         "https://api.dicebear.com/9.x/shapes/png?seed=pictile-logo-2"),
        ("11", "04_Logo", "Logo", "logo", "Logo", "几何图标", "dicebear",
         "https://api.dicebear.com/9.x/identicon/png?seed=pictile-logo-3"),
        ("12", "05_产品食物风景", "产品风景", "product", "产品", "桌面平铺", "picsum", "20"),
        ("13", "05_产品食物风景", "产品风景", "scene", "场景", "街景小车", "picsum", "45"),
        ("14", "06_文字截图地图", "文字截图", "text", "文字", "中文海报", "synthetic", "text"),
        ("15", "06_文字截图地图", "文字截图", "screenshot", "截图", "界面布局", "synthetic", "ui"),
        ("16", "07_硬负例抽象", "硬负例", "hard_negative", "硬负例", "主体过小", "picsum", "22"),
        ("17", "07_硬负例抽象", "硬负例", "hard_negative", "硬负例", "背景杂乱", "picsum", "36"),
        ("18", "07_硬负例抽象", "硬负例", "hard_negative", "硬负例", "低对比雾景", "picsum", "44"),
        ("19", "08_简单正例", "简单正例", "other", "简单正例", "干净杯子", "picsum", "30"),
        ("20", "08_简单正例", "简单正例", "other", "简单正例", "干净桌面", "picsum", "2"),
    ]

    items = []
    for num, folder, chinese_type, final_type, short, desc, kind, ref in specs:
        ext = ".png" if kind in {"dicebear", "synthetic"} else ".jpg"
        path = out / folder / f"{num}_{chinese_type}_{desc}{ext}"
        source_url = ref
        download_url = ref
        author = ""
        license = "unknown"
        source_kind = "web"
        note = ""

        if kind == "picsum":
            pid = ref
            source_url = f"https://picsum.photos/id/{pid}"
            download_url = f"https://picsum.photos/id/{pid}/1200/1200"
            m = meta.get(pid, {})
            author = m.get("author", "Picsum")
            license = "Unsplash License (via Picsum)"
            note = f"Picsum id {pid}"
        elif kind == "dicebear":
            author = "DiceBear"
            license = "DiceBear style license (verify)"
            source_kind = "generated"
            note = ""
        elif kind == "web":
            author = "randomuser.me" if "randomuser" in ref else "placedog.net"
            license = "unknown (test only)"
            note = "128×128 低分辨率" if "randomuser" in ref else "placeholder service"
        else:
            source_url = "generated locally"
            download_url = "generated locally"
            author = "scripts/stage_t00.py"
            license = "CC0 (self-generated)"
            source_kind = "generated"
            note = "Pillow 生成"

        if not path.exists() or path.stat().st_size == 0:
            if kind == "synthetic":
                if ref == "text":
                    synthetic_text(path)
                else:
                    synthetic_ui(path)
            else:
                download(download_url, path)

        with Image.open(path) as im:
            size = f"{im.width}x{im.height}"
        if kind == "dicebear":
            note = f"{size} 生成头像"
        items.append({
            "num": num, "path": path, "chinese_type": chinese_type,
            "final_type": final_type, "short": short, "desc": desc,
            "source_url": source_url, "download_url": download_url,
            "author": author, "license": license, "source_kind": source_kind,
            "note": note, "size": size, "sha256": sha256(path),
        })
        print(f'{num} {path.name}  {size}')

    contact_sheet(items, out / "T00_总览.jpg")
    write_manifest(items, out)
    write_review(items, out)
    write_readme(out)
    print(f"\nstaged: {out}")
    print(f"review: {out / 'T00_总览.jpg'}  and  {out / '清单.csv'}")


if __name__ == "__main__":
    main()
