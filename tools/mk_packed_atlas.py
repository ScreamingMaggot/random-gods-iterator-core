"""离线打包运行时真正需要的图集碎片，替掉浏览器里解 40 Mpx 合并大图的开销。

背景：web/atlas/subN.png 是 2000x3200 ~ 2000x4800 的合并图集（5 张共约 40 Mpx）。
paintTiles 只用到若干 5x7 tile 的母题块、paintFlat 只用到若干 20x20 单 tile，
但浏览器必须整张解码。实测无头 Edge 里 25s 虚拟时间都解不完，页面卡在"载入…"。

做法：按索引挑出有限数量、且在亮度上铺开取样的块与 tile，
拷进一张紧凑的 packed_subN.png（约 0.7 Mpx/张），并把索引里的 sx/sy 改写为 packed 坐标。
运行时只解小包，且 tiles.js 的绘制逻辑一行都不用改。
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

# 把借来的 tile 亮度映射进 palette23 的结构渐变（黑->暗青->中青->薄荷）。
# 依据本项目的色彩法则：青绿=机器结构，跳出调色板的红/蓝紫=活体对象。
# 原图块里的红与蓝紫是"作者给结构上的色"，若原样搬进来，结构就抢了活体的语义，
# 画面会变成一堆高饱和紫红色板。所以纹理只保留亮度信息，色相一律换成青绿档。
PAL = np.asarray(Image.open(ROOT / "ref" / "palettes" / "palette23.png").convert("RGB"), float)
RAMP = PAL[2]            # 黑 -> #63dfbd 薄荷
DARKR = PAL[6]           # 暖黑 -> 暗青


def to_struct(rgb_np):
    a = rgb_np.astype(np.float32)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    t = np.clip(lum / 255.0, 0, 1) ** 0.85 * (len(RAMP) - 1)
    lo = np.floor(t).astype(int); hi = np.minimum(lo + 1, len(RAMP) - 1); fr = (t - lo)[..., None]
    out = RAMP[lo] * (1 - fr) + RAMP[hi] * fr
    # 最暗的一档留在暖黑轴上，避免整片发绿
    very = (lum < 18)[..., None]
    return np.where(very, DARKR[0], out).astype(np.uint8)
BLOCK_PX = (BW * TILE, BH * TILE)          # 100 x 140
MAX_BLOCKS = 56
MAX_TILES = 96
COLS = 8


def spread(items, n, key="bright"):
    """按亮度排序后等距取样 n 个，保证暗/中/亮都有，而不是全取最暗。"""
    s = sorted(items, key=lambda d: d[key])
    if len(s) <= n:
        return s
    return [s[int(i * (len(s) - 1) / (n - 1))] for i in range(n)]


def pack(sub_id, meta, idx):
    src = Image.open(ATLAS / Path(meta["file"]).name).convert("RGB")
    blocks = spread(idx["blocks"], MAX_BLOCKS)
    tiles = spread(idx["lit"], MAX_TILES)

    bw, bh = BLOCK_PX
    W = COLS * bw
    block_rows = (len(blocks) + COLS - 1) // COLS
    tile_rows = (len(tiles) + (W // TILE) - 1) // (W // TILE)
    H = block_rows * bh + tile_rows * TILE
    out = Image.new("RGB", (W, H), (8, 4, 5))

    new_blocks = []
    for i, b in enumerate(blocks):
        x, y = (i % COLS) * bw, (i // COLS) * bh
        blk = np.asarray(src.crop((b["sx"], b["sy"], b["sx"] + bw, b["sy"] + bh)), np.uint8)
        out.paste(Image.fromarray(to_struct(blk)), (x, y))
        new_blocks.append({**b, "sx": x, "sy": y})
    new_tiles = []
    per = W // TILE
    y0 = block_rows * bh
    for i, t in enumerate(tiles):
        x, y = (i % per) * TILE, y0 + (i // per) * TILE
        tl = np.asarray(src.crop((t["sx"], t["sy"], t["sx"] + TILE, t["sy"] + TILE)), np.uint8)
        out.paste(Image.fromarray(to_struct(tl)), (x, y))
        new_tiles.append({**t, "sx": x, "sy": y})

    name = f"packed_sub{sub_id}.png"
    out.save(ATLAS / name, optimize=True)
    doc = {"name": meta["name"], "file": "atlas/" + name, "tile": TILE,
           "blocks": new_blocks, "lit": new_tiles,
           "srcTiles": {"blocks": len(idx["blocks"]), "lit": len(idx["lit"])}}
    (ATLAS / f"sub{sub_id}.packed.json").write_text(json.dumps(doc, separators=(",", ":")))
    return out.size, len(blocks), len(tiles)


def main() -> int:
    for p in sorted(ATLAS.glob("sub?.index.json")):
        sid = p.name[3]
        meta = json.loads((ATLAS / "manifest.json").read_text(encoding="utf-8"))["subs"][sid]
        idx = json.loads(p.read_text(encoding="utf-8"))
        size, nb, nt = pack(sid, meta, idx)
        print("[ok] sub%s %-26s packed %dx%d  块 %d/%d  tile %d/%d"
              % (sid, idx["name"], size[0], size[1], nb, idx["blocks"].__len__(), nt, len(idx["lit"])))
    tot = sum((ATLAS / f"packed_sub{i}.png").stat().st_size for i in range(5)) / 1e6
    big = sum((ATLAS / f"sub{i}.png").stat().st_size for i in range(5)) / 1e6
    print("[cmp] packed 合计 %.2f MB，原合并图集 %.2f MB" % (tot, big))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
