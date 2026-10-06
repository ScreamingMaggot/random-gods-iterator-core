#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ASCII 分支取景器：无头 msedge 截 /ascii/ 的关键帧，回报客观亮度/红/混色。
用法: python tools/shoot_ascii.py --seq 8,125,196
"""
import argparse, io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "http://127.0.0.1:8712/ascii/index.html"

def stats(page):
    return page.evaluate("""() => {
      const cv=document.getElementById('stage'), g=cv.getContext('2d');
      const d=g.getImageData(0,0,cv.width,cv.height).data;
      let sum=0,n=0,bright=0,red=0,mix=0; const hist=new Array(8).fill(0);
      for(let i=0;i<d.length;i+=4){const r=d[i],gg=d[i+1],b=d[i+2];const v=r*.3+gg*.6+b*.1;
        sum+=v;n++;if(v>120)bright++;if(r>150&&r>gg+40)red++;if(Math.min(r,gg,b)>50&&v>60)mix++;
        hist[Math.min(7,v>>5)]++;}
      return {w:cv.width,h:cv.height,mean:sum/n,bright:bright/n,red:red/n,mix:mix/n,hist,
              err:(document.getElementById('err')||{}).textContent||''};
    }""")

def shoot(t, name, wait=3.0):
    from playwright.sync_api import sync_playwright
    url = BASE + "?auto=1&t=%g" % t
    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="msedge", headless=True,
                                args=["--use-angle=swiftshader", "--disable-gpu-sandbox"])
        pg = br.new_page(viewport={"width": 1280, "height": 860})
        msgs=[]; pg.on("pageerror", lambda e: msgs.append(str(e)))
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_function("()=>window.__ready===true", timeout=60000)
        pg.evaluate("(v)=>{window.__seek(v)}", t)
        pg.wait_for_timeout(int(wait*1000))
        box = pg.locator("#stage").bounding_box()
        pg.screenshot(path=os.path.join(ROOT,"out",name+".png"),
                      clip={"x":box["x"],"y":box["y"],"width":box["width"],"height":box["height"]})
        st = stats(pg); br.close()
    st["url"]=url; st["errors"]=msgs[:6]; return st

def gate_test():
    """不带 ?auto 打开：确认点击门可见、预览帧已渲染（非黑），并截图。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="msedge", headless=True,
                                args=["--use-angle=swiftshader", "--disable-gpu-sandbox"])
        pg = br.new_page(viewport={"width": 1280, "height": 860})
        errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_function("()=>window.__ready===true", timeout=60000)
        pg.wait_for_timeout(2500)
        info = pg.evaluate("""()=>{
          const g=document.getElementById('gate'), cs=getComputedStyle(g);
          return {gateDisplay:cs.display, gateText:(g.innerText||'').slice(0,40),
                  err:(document.getElementById('err')||{}).textContent||''};
        }""")
        st = stats(pg)
        pg.screenshot(path=os.path.join(ROOT, "out", "ascii_gate.png"))
        br.close()
    st["gate"]=info; st["errors"]=errs[:6]; return st
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--seq",default="8,125,196"); ap.add_argument("--gate",action="store_true"); a=ap.parse_args()
    if a.gate:
        print(json.dumps(gate_test(), ensure_ascii=False)); return
    for ts in a.seq.split(","):
        t=float(ts); st=shoot(t,"ascii_t%g"%t); st["t"]=t
        print(json.dumps(st,ensure_ascii=False))
if __name__=="__main__": main()
