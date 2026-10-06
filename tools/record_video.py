#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐帧出片：无头 msedge 每帧 __step()+截图 → out/frames/%05d.png，再 ffmpeg 30fps 合 mp3 → mp4。
与实时无关，帧率精确、动画平滑。
用法: python tools/record_video.py            # 全片 ~5980 帧
      python tools/record_video.py --smoke 90 # 只截前 90 帧(3s)冒烟
"""
import os, sys, subprocess, time, shutil
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
FR = os.path.join(OUT, "frames")
FF = r"D:\Enviornment\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
MP3 = os.path.join(ROOT, "resource", "Random Gods (Theme III) - James Primate.mp3")
W, H, FPS = 1400, 900, 30

smoke = None
if "--smoke" in sys.argv:
    smoke = int(sys.argv[sys.argv.index("--smoke") + 1])
mp4 = os.path.join(OUT, "rg_smoke.mp4" if smoke else "Random Gods - 迭代器核心.mp4")
shutil.rmtree(FR, ignore_errors=True); os.makedirs(FR, exist_ok=True)

t0 = time.time()
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True, args=[
        "--use-angle=swiftshader", "--disable-gpu-sandbox",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-features=CalculateNativeWinOcclusion"])
    ctx = b.new_context(viewport={"width": W, "height": H}, accept_downloads=True)
    pg = ctx.new_page()
    pg.goto("http://127.0.0.1:8712/ascii/index.html?auto=1&t=0", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_function("()=>window.__ready===true", timeout=60000)
    pg.evaluate("()=>window.__reset()")
    stage = pg.locator("#stage")
    n = pg.evaluate("()=>window.__frames")
    if smoke: n = min(n, smoke)
    print("total frames:", n, flush=True)
    for i in range(n):
        pg.evaluate("()=>window.__step()")
        stage.screenshot(path=os.path.join(FR, "%05d.png" % i))
        if i % 500 == 0: print("frame %d/%d  %.0fs" % (i, n, time.time() - t0), flush=True)
    b.close()
print("captured %d frames in %.0fs" % (n, time.time() - t0), flush=True)

cmd = [FF, "-y", "-framerate", str(FPS), "-i", os.path.join(FR, "%05d.png")]
if not smoke:
    cmd += ["-i", MP3]
cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium"]
if not smoke:
    cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
cmd += [mp4]
r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stderr[-500:], flush=True)
print("MP4:", mp4, os.path.exists(mp4), flush=True)
