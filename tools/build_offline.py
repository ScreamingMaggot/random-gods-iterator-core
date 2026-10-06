#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把整套渲染器打成一个自包含 HTML：双击即可在 Edge 里打开，不依赖服务、不读任何外部文件。

做法：
  1  房间彩色图由 tools/mk_offline_assets.py 用**已与 roomtex.js 逐像素对账的** numpy 着色器
     预先解好，拼成一张无损 WebP 图集（索引图 23 MB -> 彩色图集 2 MB，且离线端不必带解码器与调色板）。
  2  把 web/src/*.js 按 import 图打包成一段模块脚本：每个模块包进一个 async 工厂，
     `import {a} from "./x.js"` 改写成 `const {a} = await __req("./x.js")`。
     file:// 下 ES module 会被 CORS 挡，所以必须内联；顶层 await 要求工厂是 async 的。
  3  pack.json / 图集 / 音频 内联成一个 application/json 块，运行时挂到 window.__OFFLINE_DATA，
     代码里的 OFFLINE 分支就改走内联数据（同一套源码，开发版仍走 fetch）。

用法：python tools/build_offline.py [输出名]
"""
import base64
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "web", "src")
OFF = os.path.join(ROOT, "out", "offline")

RE_IMPORT = re.compile(r'^import\s*\{([^}]*)\}\s*from\s*"([^"]+)"\s*;?\s*$', re.M)
RE_EXPORT = re.compile(r'^export\s+(async\s+function|function|class|const|let|var)\s+([A-Za-z_$][\w$]*)', re.M)


def bundle(entry="./main.js"):
    """按 import 图递归打包，返回 (脚本正文, 模块清单)。"""
    seen, order = set(), []

    def walk(spec):
        if spec in seen:
            return
        seen.add(spec)
        text = open(os.path.join(SRC, spec.replace("./", "")), encoding="utf-8").read()
        for m in RE_IMPORT.finditer(text):
            walk(m.group(2))
        order.append((spec, text))

    walk(entry)
    parts = []
    for spec, text in order:
        deps = []
        def sub(m):
            deps.append(m.group(2))
            names = ",".join(n.strip() for n in m.group(1).split(",") if n.strip())
            return "const {%s} = await __req(\"%s\");" % (names, m.group(2))
        body = RE_IMPORT.sub(sub, text)
        names = [m.group(2) for m in RE_EXPORT.finditer(body)]
        body = RE_EXPORT.sub(lambda m: "%s %s" % (m.group(1), m.group(2)), body)
        parts.append('__def("%s", async () => {\n%s\nreturn {%s};\n});' % (spec, body, ",".join(names)))
    prelude = ("const __MODS = {}, __CACHE = {};\n"
               "function __def(id, fn) { __MODS[id] = fn; }\n"
               "function __req(id) {\n"
               "  if (!__CACHE[id]) {\n"
               "    if (!__MODS[id]) throw new Error('缺模块 ' + id);\n"
               "    __CACHE[id] = __MODS[id]();          // 工厂是 async：顶层 await 才能用\n"
               "  }\n  return __CACHE[id];\n}\n")
    return prelude + "\n".join(parts) + "\nawait __req(\"%s\");\n" % entry, [s for s, _ in order]


def data_uri(path, mime):
    with open(path, "rb") as f:
        return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode("ascii"))


def build(out_name):
    atlas = os.path.join(OFF, "rooms.webp")
    if not os.path.isfile(atlas):
        print("缺少 out/offline/rooms.webp —— 先跑 python tools/mk_offline_assets.py 350")
        return 1
    rooms = json.loads(open(os.path.join(OFF, "rooms.json"), encoding="utf-8").read())
    pack = json.loads(open(os.path.join(ROOT, "out", "pack.json"), encoding="utf-8").read())
    audio = os.path.join(ROOT, "resource", "Random Gods (Theme III) - James Primate.mp3")

    data = {"pack": pack, "rooms": rooms, "atlas": data_uri(atlas, "image/webp"),
            "audio": data_uri(audio, "audio/mpeg")}
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")

    js, mods = bundle()
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    tag = '<script type="module" src="./src/main.js"></script>'
    assert tag in html, "index.html 的入口脚本标签变了，构建脚本要跟着改"
    html = html.replace(tag,
                        '<script id="data" type="application/json">%s</script>\n'
                        '<script>window.__OFFLINE_DATA = JSON.parse(document.getElementById("data").textContent);</script>\n'
                        '<script type="module">\n%s</script>' % (blob, js))
    html = html.replace("<title>RANDOM GODS — 迭代器核心舱运算全景</title>",
                        "<title>RANDOM GODS — 迭代器核心舱运算全景（离线版）</title>")
    dst = os.path.join(ROOT, "out", out_name)
    open(dst, "w", encoding="utf-8", newline="\n").write(html)
    sz = os.path.getsize(dst)
    print("模块 %d 个：%s" % (len(mods), " ".join(m.replace("./", "") for m in mods)))
    print("房间图 %d 间  音频 %s" % (len(rooms["rooms"]), os.path.getsize(audio) // 1024))
    print("-> %s  %.2f MB" % (dst, sz / 1048576))
    return 0


if __name__ == "__main__":
    sys.exit(build(sys.argv[1] if len(sys.argv) > 1 else "RANDOM_GODS_offline.html"))
