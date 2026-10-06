#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线逐帧取景器：无头 Edge + playwright，把渲染器产物截成 PNG 并回报客观亮度。

用法:
    python tools/shoot.py --t 125 --room SS_LAB1 --zoom 3 --name shot_lab1
    python tools/shoot.py --overview --t 40 --name shot_overview
    python tools/shoot.py --seq 0,30,60,90,120,150,180 --name seq
"""
import argparse
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8712/web/index.html"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def stats(page):
    """把画布像素拉回 Python 侧算亮度分布（判"死黑"必须用数值，不能靠眼睛）。"""
    return page.evaluate("""() => {
      const cv = document.getElementById('stage');
      const g = cv.getContext('2d');
      const d = g.getImageData(0, 0, cv.width, cv.height).data;
      let sum = 0, dark = 0, bright = 0, n = 0, maxv = 0;
      const hist = new Array(8).fill(0);
      const rs = new Array(8).fill(0), gs = new Array(8).fill(0), bs = new Array(8).fill(0);
      for (let i = 0; i < d.length; i += 4) {
        const v = (d[i] * 0.299 + d[i+1] * 0.587 + d[i+2] * 0.114);
        sum += v; n++; maxv = Math.max(maxv, v);
        if (v < 8) dark++; else if (v > 200) bright++;
        const b = Math.min(7, v >> 5); hist[b]++;
        rs[b] += d[i]; gs[b] += d[i+1]; bs[b] += d[i+2];
      }
      return {w: cv.width, h: cv.height, mean: sum / n, dark: dark / n, bright: bright / n,
              max: maxv, hist, rgb: [rs, gs, bs].map(a => a.map((v, i) => v / (hist[i] || 1))),
              err: (document.getElementById('err') || {}).textContent || '',
              fps: (document.getElementById('fps') || {}).textContent || ''};
    }""")


def shoot(t, room=None, zoom=None, overview=False, name="shot", wait=8.0):
    from playwright.sync_api import sync_playwright
    q = "?auto=1&t=%g" % t
    if room:
        q += "&room=%s" % room
    if zoom:
        q += "&zoom=%s" % zoom
    url = BASE + q
    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="msedge", headless=True,
                                args=["--use-angle=swiftshader", "--disable-gpu-sandbox"])
        pg = br.new_page(viewport={"width": 1280, "height": 760})
        msgs = []
        pg.on("console", lambda m: msgs.append("%s: %s" % (m.type, m.text)) if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: msgs.append("pageerror: " + str(e)))
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_function("() => window.__ready === true", timeout=120000)
        pg.evaluate("(v) => { window.__seek(v); }", t)
        if overview:
            pg.evaluate("() => { window.__cam.toggleOverview(); }")
        pg.wait_for_timeout(int(wait * 1000))
        box = pg.locator("#stage").bounding_box()
        pg.screenshot(path=os.path.join(ROOT, "out", name + ".png"),
                      clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]})
        st = stats(pg)
        br.close()
    st["url"] = url
    st["console"] = msgs[:12]
    return st


def lt_ab(room):
    """把 roomtex.js 的 CPU 着色结果导回来，与 numpy 参照实现逐像素对账。"""
    import base64
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="msedge", headless=True,
                                args=["--use-angle=swiftshader", "--disable-gpu-sandbox"])
        pg = br.new_page(viewport={"width": 1280, "height": 760})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE + "?auto=1&nobake=1&t=0", wait_until="domcontentloaded", timeout=60000)
        try:
            pg.wait_for_function("() => window.__lt || (document.getElementById('err')||{}).textContent",
                                 timeout=90000)
        except Exception as e:
            print("等待失败:", str(e)[:120])
        diag = pg.evaluate("""() => ({lt: !!window.__lt, rt: !!(window.__lt && window.__lt.rt),
            ready: !!window.__ready, err: (document.getElementById('err')||{}).textContent || '',
            boot: (window.__bootErrs||[]).slice(0,3).join(' ;; ').slice(0,400),
            load: (document.getElementById('loading')||{}).textContent || ''})""")
        print("DIAG", diag, "EVENTS", errs[:4], flush=True)
        if not diag["rt"]:
            br.close()
            return
        res = pg.evaluate("""async (id) => {
          const t0 = performance.now();
          let r = null, thrown = '';
          try { r = await window.__lt.render(id); } catch (e) { thrown = String(e && e.stack || e); }
          const ms = performance.now() - t0;
          if (!r) return {null: true, thrown, ltErr: window.__ltErr || '', ms};
          const g = r.col.getContext('2d');
          const d = g.getImageData(0, 0, r.col.width, r.col.height).data;
          let sum = 0, n = 0; const hist = new Array(8).fill(0);
          for (let i = 0; i < d.length; i += 4) {
            const v = d[i] * 0.299 + d[i+1] * 0.587 + d[i+2] * 0.114;
            sum += v; n++; hist[Math.min(7, v >> 5)]++;
          }
          return {png: r.col.toDataURL('image/png'), mean: sum / n, hist, ms,
                  reqs: (window.__ltReqs || []).slice(0, 6),
                  bakeMs: window.__bakeMs || null, w: r.col.width, h: r.col.height};
        }""", room)
        br.close()
    if not res or res.get("null"):
        print("%s: 渲染为空  thrown=%s  ltErr=%s  %.0fms" %
              (room, (res or {}).get("thrown", "")[:300], (res or {}).get("ltErr", "")[:300],
               (res or {}).get("ms", 0)))
        return
    raw = base64.b64decode(res["png"].split(",")[1])
    open(os.path.join(ROOT, "out", "ltjs_%s.png" % room), "wb").write(raw)
    print("%s js mean %.1f hist %s (%dx%d) render %.0fms reqs %s errs %d" %
          (room, res["mean"], np_round(res["hist"], res["w"] * res["h"]), res["w"], res["h"],
           res["ms"], res.get("reqs"), len(errs)))


def np_round(h, n):
    return [round(x / n, 3) for x in h]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--t", type=float, default=0.0)
    ap.add_argument("--seq", default=None)
    ap.add_argument("--room", default=None)
    ap.add_argument("--zoom", default=None)
    ap.add_argument("--overview", action="store_true")
    ap.add_argument("--lt", default=None, help="导出该房间的 CPU 着色结果做 A/B")
    ap.add_argument("--name", default="shot")
    ap.add_argument("--wait", type=float, default=8.0)
    a = ap.parse_args()
    if a.lt:
        for r in a.lt.split(","):
            lt_ab(r)
        return
    ts = [float(x) for x in a.seq.split(",")] if a.seq else [a.t]
    rep = []
    for t in ts:
        nm = a.name if a.seq is None else "%s_t%g" % (a.name, t)
        st = shoot(t, a.room, a.zoom, a.overview, nm, a.wait)
        st["name"] = nm
        rep.append(st)
        print(json.dumps(st, ensure_ascii=False))


if __name__ == "__main__":
    main()
