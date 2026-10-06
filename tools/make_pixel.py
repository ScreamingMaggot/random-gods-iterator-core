#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 ascii/src/cpuascii.js 派生一个"像素版"渲染器，写到 pixel/src/cpupixel.js。

原则：只读 ascii/ 分支，绝不修改它。所有改动都在 pixel/ 目录内。
做法：字符网格 (列,行,RGB,强度) 保持不变，只把 5 处 fillText 字形输出换成 fillRect 色块。
"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "ascii", "src", "cpuascii.js")
DST = os.path.join(ROOT, "pixel", "src", "cpupixel.js")

s = open(SRC, encoding="utf-8").read()

CELL = '''  // 像素模式：同一套 (列,行,RGB,强度) 网格，字形换成 cw×chh 色块
  function cell(g, col, row, rgb, a, ch) {
    g.fillStyle = `rgba(${rgb[0] | 0},${rgb[1] | 0},${rgb[2] | 0},${clamp(a / 255, 0, 1)})`;
    g.fillRect(Math.round(ox + col * cw), Math.round(oy + row * chh), Math.ceil(cw), Math.ceil(chh));
  }
'''

REPS = [
    # 0) 相对导入改成指回 ascii/src（本副本位于 pixel/src，不能直接 ./util.js）
    (
        'import { clamp, makeCam, torus } from "./util.js";',
        'import { clamp, makeCam, torus } from "../../ascii/src/util.js";'
    ),
    # 1) 导出名 + 插入 cell 辅助
    (
        'export function createCpuAscii(cpu, pack, COLS = 128, ROWS = 58) {',
        'export function createCpuPixel(cpu, pack, COLS = 128, ROWS = 58) {'
    ),
    (
        '  const bgc = document.createElement("canvas"); const bgx = bgc.getContext("2d");   // 背景离屏层（做毛玻璃）',
        '  const bgc = document.createElement("canvas"); const bgx = bgc.getContext("2d");   // 背景离屏层（做毛玻璃）\n\n' + CELL
    ),
    # 2) 底部频谱柱
    (
        '''        g2.fillText(k === h - 1 ? "_" : "|", ox + (x + 0.5) * cw, oy + (y + 0.82) * chh); }''',
        '''        cell(g2, x, y, [72, 175, 210], 255 * clamp((1 - k / bandH) * 0.92, 0, 0.95), k === h - 1 ? "_" : "|"); }'''
    ),
    # 3) 计算之心 put
    (
        '''    const put = (col, row, ch, rgb, a) => { if (row > cy2) return; g2.fillStyle = `rgba(${rgb[0] | 0},${rgb[1] | 0},${rgb[2] | 0},${clamp(a / 255, 0, 1)})`; g2.fillText(ch, ox + (col + 0.5) * cw, oy + (row + 0.82) * chh); };''',
        '''    const put = (col, row, ch, rgb, a) => { if (row > cy2) return; cell(g2, col, row, rgb, a, ch); };'''
    ),
    # 4) 加载环 put
    (
        '''    const put = (col, row, ch, rgb, a) => { g2.fillStyle = `rgba(${rgb[0] | 0},${rgb[1] | 0},${rgb[2] | 0},${clamp(a / 255, 0, 1)})`; g2.fillText(ch, ox + (col + 0.5) * cw, oy + (row + 0.82) * chh); };''',
        '''    const put = (col, row, ch, rgb, a) => { cell(g2, col, row, rgb, a, ch); };'''
    ),
    # 5) 背景字符雨
    (
        '''        g2.fillStyle = `rgba(${k === 0 ? "120,165,240" : "34,74,165"},${clamp(a * 0.6, 0, 0.65)})`;
        g2.fillText(String.fromCharCode(48 + ((bit(c * 13 + k, (st.tick >> 2)) * 10) | 0)), ox + (gx + 0.5) * cw, oy + (y + 0.82) * chh); }''',
        '''        cell(g2, gx, y, k === 0 ? [120, 165, 240] : [34, 74, 165], 255 * clamp(a * 0.6, 0, 0.65), String.fromCharCode(48 + ((bit(c * 13 + k, (st.tick >> 2)) * 10) | 0))); }'''
    ),
    # 6) 主网格遍历（画面主体）
    (
        '''    for (let p = 0; p < N; p++) { if (gCh[p] === 32 || gA[p] < 12) continue; const x = p % COLS, y = (p / COLS) | 0; ctx.fillStyle = `rgba(${gR[p]},${gG[p]},${gB[p]},${Math.min(255, ((gA[p] >> 4) << 4) * fade * flick) / 255})`; ctx.fillText(String.fromCharCode(gCh[p]), ox + (x + 0.5) * cw, oy + (y + 0.82) * chh); }''',
        '''    for (let p = 0; p < N; p++) { if (gCh[p] === 32 || gA[p] < 12) continue; const x = p % COLS, y = (p / COLS) | 0; cell(ctx, x, y, [gR[p], gG[p], gB[p]], Math.min(255, ((gA[p] >> 4) << 4) * fade * flick), String.fromCharCode(gCh[p])); }'''
    ),
    # 7) 像素风：背景层不再毛玻璃模糊
    (
        '''ctx.save(); ctx.filter = "blur(1.6px)";''',
        '''ctx.save(); ctx.filter = "none";'''
    ),
]

for old, new in REPS:
    if old not in s:
        print("!! 未匹配（源文件可能已变动）:\n" + old[:110])
        sys.exit(2)
    s = s.replace(old, new, 1)

os.makedirs(os.path.dirname(DST), exist_ok=True)
open(DST, "w", encoding="utf-8").write(s)
print("已生成 %s  (%d 字节, 替换 %d 处)" % (DST, len(s), len(REPS)))
