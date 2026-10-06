"""把 tiles.js 里那段"扫描图集求 tile/块亮度与色相"的活搬到离线，产出 subN.index.json。

动机：原实现每次启动都要在浏览器里对 5 张 6.4~9.6 Mpx 的合并图集做
getImageData + 约 48M 次采样内循环，实测十几秒都出不来。这件事是纯确定性的，
与浏览器无关，所以离线算一次存成索引，运行时只 drawImage。

产出的字段与 tiles.js 的读法逐一对齐（含它原有的取样偏移）：
  lit[]    {sx,sy,bright,kind}   bright = 该 tile 左列 y 方向每 4px 采一次的 R+G+B 累加
  blocks[] {sx,sy,w,h,kind,bright,lit}  块 = 5x7 tile；px/py 各再偏移一个 TILE（沿用原码）
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
ATLAS = ROOT / "web" / "atlas"
TILE = 20
BW, BH = 5, 7


def kind_of(r, g, b):
    if b > r + 15 or (b > 120 and r < 90):
        return "v"
    if r > g + 12 and r > b + 12:
        return "r"
    return "n"


def build(sub_id, meta):
    img = Image.open(ATLAS / Path(meta["file"]).name).convert("RGB")
    a = np.asarray(img, np.int16)
    H, W = a.shape[0], a.shape[1]
    lit, blocks = [], []
    for slot in meta["slots"]:
        sx0, sy0, sw, sh = slot["x"], slot["y"], slot["w"], slot["h"]
        for ty in range(sh):
            for tx in range(sw):
                px, py = (sx0 + tx) * TILE, (sy0 + ty) * TILE
                if px >= W or py >= H:
                    continue
                col = a[py:py + TILE:4, px]
                bright = int(col.sum())
                if bright <= 900:
                    continue
                r, g, b = a[min(py + TILE // 2, H - 1), min(px + TILE // 2, W - 1)]
                lit.append({"sx": px, "sy": py, "bright": bright, "kind": kind_of(int(r), int(g), int(b))})
        for by in range(0, sh - BH + 1, BH):
            for bx in range(0, sw - BW + 1, BW):
                px, py = (sx0 + bx) * TILE + TILE, (sy0 + by) * TILE + TILE
                if px >= W or py >= H:
                    continue
                x1 = min(px + BW * TILE, W - 1)
                y1 = min(py + BH * TILE, H - 1)
                patch = a[py:y1 + 1:4, px:x1 + 1:4]
                s3 = patch.sum(2)
                n = (BH * TILE // 4) * (BW * TILE // 4)
                litfrac = float((s3 > 40).mean())
                if litfrac < 0.12:
                    continue
                r, g, b = a[py, px]
                blocks.append({"sx": (sx0 + bx) * TILE, "sy": (sy0 + by) * TILE,
                               "w": BW * TILE, "h": BH * TILE, "kind": kind_of(int(r), int(g), int(b)),
                               "bright": round(float(s3.sum()) / n, 2), "lit": round(litfrac, 3)})
    return {"lit": lit, "blocks": blocks, "name": meta["name"], "file": meta["file"],
            "cols": meta.get("cols"), "rows": meta.get("rows"), "slots": meta["slots"]}


def main() -> int:
    man = json.loads((ATLAS / "manifest.json").read_text(encoding="utf-8"))
    for k, v in sorted(man["subs"].items()):
        idx = build(k, v)
        out = ATLAS / f"sub{k}.index.json"
        out.write_text(json.dumps(idx, separators=(",", ":"), ensure_ascii=False))
        print("[ok] %-22s lit %5d  blocks %5d  -> %s (%.1f KB)"
              % (v["name"], len(idx["lit"]), len(idx["blocks"]), out.name, out.stat().st_size / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
