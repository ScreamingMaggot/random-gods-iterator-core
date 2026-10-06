"""从四张官方渲染图提取像素调色板与明度分布，供渲染器锁定色域。

像素风的成败在色板：这里不做"好看的颜色"，只统计参考图里真实存在的颜色。
方法：中位切分 k-means（k=24）-> 按像素占比排序 -> 量化到 5-6-5 便于像素对齐 ->
      另出明度直方图（判断画面整体有多暗，决定暗部该留多少级）。
输出 out/palette.json + out/verify_palette.png。
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "resource"
OUT = ROOT / "out" / "palette.json"
PLOT = ROOT / "out" / "verify_palette.png"
K = 24


def load_pixels(p):
    from PIL import Image
    im = Image.open(p).convert("RGB")
    a = np.asarray(im, np.float32)
    return a.reshape(-1, 3), im.size


def kmeans(px, k, seed=0, iters=12):
    rng = np.random.RandomState(seed)
    c = px[rng.choice(len(px), k, replace=False)].copy()
    for _ in range(iters):
        d = ((px[:, None, :] - c[None, :, :]) ** 2).sum(2)
        lab = d.argmin(1)
        new = c.copy()
        for j in range(k):
            m = lab == j
            if m.any():
                new[j] = px[m].mean(0)
        if np.allclose(new, c, atol=1.0):
            c = new
            break
        c = new
    d = ((px[:, None, :] - c[None, :, :]) ** 2).sum(2)
    lab = d.argmin(1)
    counts = np.bincount(lab, minlength=k)
    order = np.argsort(-counts)
    return c[order], (counts[order] / len(px))


def main() -> int:
    assert RES.exists(), RES
    allpx, per_img = [], {}
    for p in sorted(RES.glob("*.png")):
        px, size = load_pixels(p)
        rng = np.random.RandomState(0)
        px = px[rng.choice(len(px), min(40000, len(px)), replace=False)]
        per_img[p.name] = {"size": list(size), "n": int(len(px))}
        allpx.append(px)
        print("[ok] %-46s %dx%d" % (p.name, size[0], size[1]))
    px = np.concatenate(allpx, 0)
    cents, frac = kmeans(px, K)
    lum = (0.2126 * cents[:, 0] + 0.7152 * cents[:, 1] + 0.0722 * cents[:, 2]) / 255.0
    q = np.clip(np.rint(cents / 255 * np.array([31, 63, 31])) / np.array([31, 63, 31]) * 255, 0, 255).astype(int)

    out = {"k": K, "sampled_pixels": int(len(px)), "images": per_img,
           "palette": [{"hex": "#%02x%02x%02x" % tuple(int(v) for v in c),
                        "rgb": [int(v) for v in c], "q565": "#%02x%02x%02x" % tuple(int(v) for v in qq),
                        "share": round(float(w), 4), "lum": round(float(l), 3)}
                       for c, qq, w, l in zip(cents, q, frac, lum)],
           "dark_share_lum_lt_0.25": round(float(frac[lum < 0.25].sum()), 3),
           "bright_share_lum_gt_0.75": round(float(frac[lum > 0.75].sum()), 4)}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))

    print("\n=== %d 色主色板（按占比）===" % K)
    for e in out["palette"]:
        bar = "█" * max(1, int(e["share"] * 60))
        print("   %-9s lum %.2f  %5.2f%% %s" % (e["hex"], e["lum"], 100 * e["share"], bar))
    print("   明度<0.25 的像素占 %.1f%%，>0.75 的占 %.2f%%" % (100 * out["dark_share_lum_lt_0.25"],
                                                              100 * out["bright_share_lum_gt_0.75"]))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(14, 5))
        for i, e in enumerate(out["palette"]):
            ax[0].add_patch(rect((i / K, 0), (1 / K, e["share"]), color=np.array(e["rgb"]) / 255))
        ax[0].set_title("palette by pixel share")
        ax[0].set_xticks([])
        ax[1].hist(lum, weights=frac, bins=24, color="steelblue")
        ax[1].set_title("luminance distribution")
        ax[1].set_xlabel("relative luminance")
        fig.tight_layout()
        fig.savefig(str(PLOT), dpi=100)
        plt.close(fig)
        print("[ok] plot ->", PLOT.name)
    except Exception as ex:                                    # noqa: BLE001
        print("[warn] plot skipped:", ex)
    return 0


def rect(xy, wh, color):
    from matplotlib.patches import Rectangle
    return Rectangle(xy, wh[0], wh[1], color=color)


if __name__ == "__main__":
    raise SystemExit(main())
