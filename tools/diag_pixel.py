import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8712/pixel/index.html?auto=1&t=125"
with sync_playwright() as pw:
    br = pw.chromium.launch(channel="msedge", headless=True,
                            args=["--use-angle=swiftshader", "--disable-gpu-sandbox"])
    pg = br.new_page(viewport={"width": 1280, "height": 860})
    errs = []
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append("console:%s:%s" % (m.type, m.text)))
    pg.on("requestfailed", lambda r: errs.append("reqfail: %s %s" % (r.url, r.failure)))
    pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(6000)
    print("ready =", pg.evaluate("()=>window.__ready"))
    print("errEl =", pg.evaluate("()=>{const e=document.getElementById('err');return e?e.textContent:'(none)'}"))
    print("loading =", pg.evaluate("()=>{const e=document.getElementById('loading');return e?e.style.display:'(none)'}"))
    for e in errs[:10]:
        print(" -", e[:400])
    br.close()
