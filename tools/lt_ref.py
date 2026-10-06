#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 web/gallery.html 的 LevelColor pass 用 numpy 原样实现一遍，作为 roomtex.js 的对照真值。

判据：同一间房、同一调色板，两者逐像素色差应接近 0（只有抽样网格不同）。
"""
import io
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pal_cells(n):
    a = np.asarray(Image.open(os.path.join(ROOT, "web/pals/palette%d.png" % n)).convert("RGB")).astype(np.uint8)
    h, w = a.shape[:2]
    out = np.zeros((8, 32, 3), dtype=np.uint8)
    for r in range(8):
        for c in range(32):
            y = int((r + 0.5) * h / 8)
            x = int((c + 0.5) * w / 32)
            out[r, c] = a[y, x]
    return out


def decode(room, out_w=700, fog=1.0, grime=1.0, light=0.0):
    lt = np.asarray(Image.open(os.path.join(ROOT, "resource/lt/%s_1.png" % room)).convert("RGB")).astype(np.uint8)
    H, W = lt.shape[:2]
    palid = json.load(open(os.path.join(ROOT, "resource/lt/index2.json"), encoding="utf-8"))[room]["pal"]
    P = pal_cells(palid).astype(np.float32)
    nz = np.asarray(Image.open(os.path.join(ROOT, "ref/shared/noise.png")).convert("RGB"))[:, :, 0].astype(np.float32) / 255.0

    out_h = int(round(out_w * H / W))
    xs = np.minimum((np.arange(out_w) + 0.5) / out_w * W, W - 1).astype(int)
    ys = np.minimum((np.arange(out_h) + 0.5) / out_h * H, H - 1).astype(int)
    src = lt[np.ix_(ys, xs)].astype(np.float32)
    red = src[:, :, 0].copy()
    green = src[:, :, 1].copy()
    blue = src[:, :, 2]

    u = (np.arange(out_w) + 0.5)[None, :] / out_w
    v = (np.arange(out_h) + 0.5)[:, None] / out_h
    U = np.broadcast_to(u, (out_h, out_w))
    V = np.broadcast_to(v, (out_h, out_w))

    nfd = (green < 16)
    green = np.where(green >= 16, green - 16, green)
    ec = np.where(green >= 8, 100.0, green)
    green = np.where(green >= 8, green - 8, green)
    gr = green >= 4

    m30 = red % 30.0
    nu = np.floor((U * 0.5 - 0.003 * m30) % 1.0 * nz.shape[0]).astype(int)
    nv = np.floor((1.0 - V * 0.5 - 0.003 * m30) % 1.0 * nz.shape[1]).astype(int)
    n = nz[nv, nu]
    sh = np.clip((0.5 + np.sin((n - V) % 1.0 * 2 * np.pi) * 0.5 - 0.5) * 6.0 + 0.5 - light * 4.0, 0, 1)
    shadow = red > 90
    sh = np.where(shadow, sh, 1.0)                     # 与着色器一致：sh 是连续的陡坡，不是硬阈值
    red = np.where(shadow, red - 90, red)
    pc = np.clip(np.floor((red - 1) / 30), 0, 2).astype(int)
    col = np.mod(red - 1, 30)
    cix = np.clip(np.floor(col * nfd), 0, 31).astype(int)

    lit = P[pc, cix]
    dark = P[np.clip(pc + 3, 0, 7), cix]
    out = dark + (lit - dark) * sh[:, :, None]

    fogc = P[7, 1]
    n2u = np.floor((U * 2.0) % 1.0 * nz.shape[0]).astype(int)
    n2v = np.floor((V * 2.0) % 1.0 * nz.shape[1]).astype(int)
    n2 = nz[n2v, n2u]
    rb = np.sin((n2 * 4.0 + col / 12.0) * 2 * np.pi) * 0.5 + 0.5
    gc = P[6, np.clip(np.floor(5.5 + rb * 25.0).astype(int), 0, 31)]
    out = np.where(gr[:, :, None], out + (gc - out) * (0.2 * grime), out)

    # ec==100：底行取色
    bx = np.clip(((255.5 - blue) * W / 1400.0).astype(int), 0, W - 1)
    dc = lt[H - 1, bx].astype(np.float32)
    dc = np.where((pc == 2)[:, :, None], dc + (255 - dc) * (0.2 - sh[:, :, None] * 0.1), dc)
    dc = dc + (fogc - dc) * (col / 60.0)[:, :, None]
    m = (ec == 100)[:, :, None]
    out = np.where(m, out + (dc - out) * 0.7, out)
    kk = 0.9 + ((0.3 + 0.4 * sh[:, :, None]) - 0.9) * np.clip((col - 3.5) * 0.3, 0, 1)[:, :, None]
    out = np.where(m, out + (out * dc * 1.5 / 255.0 - out) * kk, out)

    out = out + (fogc - out) * np.clip(col * fog / 30.0, 0, 1)[:, :, None]
    return np.clip(out, 0, 255).astype(np.uint8), palid


def lum(a):
    return (a[:, :, 0] * 0.299 + a[:, :, 1] * 0.587 + a[:, :, 2] * 0.114)


if __name__ == "__main__":
    # 只在直接运行时重包 stdout：被 import 时再包一层会把调用方的 buffer 关掉
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    for room in sys.argv[1:] or ["ss_lab1", "ss_a01", "ss_c06"]:
        a, palid = decode(room)
        Image.fromarray(a).save(os.path.join(ROOT, "out", "ltref_%s.png" % room))
        L = lum(a.astype(np.float32))
        h = np.histogram(L, bins=8, range=(0, 256))[0] / L.size
        print("%s pal%d mean %.1f  p50 %.0f  >200 %.3f  hist %s" %
              (room, palid, L.mean(), np.median(L), (L > 200).mean(), np.round(h, 3)))
