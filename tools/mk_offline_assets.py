#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成离线版素材：把所有房间的官方 levelTexture 用**已对账的** numpy 着色器解成彩色图，
拼成一张图集 PNG，并记录每间房在图集里的格子。

离线版因此不需要携带 23 MB 的索引图、38 张调色板和解码器 —— 只带解码结果。
"""
import io
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from lt_ref import decode          # 与 web/src/roomtex.js 逐像素对账过的参照实现

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(width=700, out="out/offline"):
    os.makedirs(os.path.join(ROOT, out), exist_ok=True)
    rooms = json.load(open(os.path.join(ROOT, "out/pack.json"), encoding="utf-8"))["map"]["rooms"]
    idx2 = json.load(open(os.path.join(ROOT, "resource/lt/index2.json"), encoding="utf-8"))
    have = set(json.load(open(os.path.join(ROOT, "resource/lt/index.json"), encoding="utf-8")))

    jobs = sorted(k for k in rooms if k.lower() in have)
    cells = {}
    imgs = []
    h0 = None
    for k in jobs:
        a, pal = decode(k.lower(), out_w=width)
        a = np.ascontiguousarray(a)
        if h0 is None:
            h0 = a.shape[0]
        imgs.append(a)
        cells[k] = {"pal": pal, "h": a.shape[0], "w": a.shape[1]}
        print("  %-12s pal%-3d %dx%d" % (k, pal, a.shape[1], a.shape[0]), flush=True)

    # 网格拼接：每行 4 张，统一行高（所有房间图宽高比一致）
    per = 4
    w = width
    hs = [cells[k]["h"] for k in jobs]
    rows = (len(jobs) + per - 1) // per
    rh = max(hs)
    AW, AH = w * per, rh * rows
    atlas = np.zeros((AH, AW, 3), dtype=np.uint8)
    for i, k in enumerate(jobs):
        r, c = divmod(i, per)
        a = imgs[i]
        atlas[r * rh:r * rh + a.shape[0], c * w:c * w + a.shape[1]] = a
        cells[k]["x"] = c * w
        cells[k]["y"] = r * rh
    Image.fromarray(atlas).save(os.path.join(ROOT, out, "rooms.webp"), format="WEBP",
                                lossless=True, quality=100, method=6)
    # 键统一小写：运行时是按 levelTexture 的房名（小写）取格子
    cells = {k.lower(): v for k, v in cells.items()}
    json.dump({"cell_w": w, "cell_h": rh, "cols": per, "rooms": cells},
              open(os.path.join(ROOT, out, "rooms.json"), "w", encoding="utf-8"), ensure_ascii=False)
    sz = os.path.getsize(os.path.join(ROOT, out, "rooms.webp"))
    print("atlas %dx%d  rooms %d  无损WebP %.2f MB  (base64 %.2f MB)" %
          (AW, AH, len(jobs), sz / 1048576, sz * 4 / 3 / 1048576))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 700)
