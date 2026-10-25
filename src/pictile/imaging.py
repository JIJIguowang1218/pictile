"""Image loading and deterministic square downsample for the baseline pipeline."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


def load_square_rgb(path: str | Path, grid_size: int = 29) -> tuple[np.ndarray, dict]:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    orig_w, orig_h = im.size

    if im.mode == "P" and "transparency" in im.info:
        im = im.convert("RGBA")
    if im.mode in ("RGBA", "LA"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im).convert("RGB")
    else:
        im = im.convert("RGB")

    s = min(im.width, im.height)
    left = (im.width - s) // 2
    top = (im.height - s) // 2
    im = im.crop((left, top, left + s, top + s))

    arr = np.asarray(im)
    arr = cv2.resize(arr, (grid_size, grid_size), interpolation=cv2.INTER_AREA)
    meta = {
        "orig_size": [int(orig_w), int(orig_h)],
        "crop_size": [int(s), int(s)],
        "crop_box": [int(left), int(top), int(left + s), int(top + s)],
    }
    return arr, meta
