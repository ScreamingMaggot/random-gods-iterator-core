"""一次性清理脚本：删除过程产物与可再生中间体，保留核心资产。

保留:
  out/features.json acts.json palette.json pack.json nav_audit.json verify_features.png
  ref/src/            反编译源码（渲染算法参考，19MB）
  ref/ss_tiles/       219 张图块原图（美术参考核心，68MB）
  resource/lt/        74 张解码 levelTexture（当前渲染输入，22MB）
  ref/shared/         maze/glyphs/corals/circuit 共用图集
  web/pals/           38 个房间调色板
删除:
  .playwright-cli/            浏览器快照与日志
  tools/__pycache__/
  web/atlas/                  图集切片，可由 ref/mk_atlas.py 重新生成
  out/*.png                   过程截图（保留 verify_features.png）
  ref/_tile_fmt_out.txt       临时记录，内容已并入 SCENE_NOTES 第 10 节
  ref/scan_bundles.py         Addressables 字体图集扫描（已确认无关）
  ref/export_atlas.py         同上
  ref/find_iter_refs.py       DLL 字符串反查（已完成使命）
  ref/dig.py                  临时探查
用法: python tools/cleanup.py
"""
from __future__ import annotations

import io
import shutil
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
KEEP_OUT_PNG = {"verify_features.png"}


def size_of(p: Path) -> int:
    t = 0
    for f in p.rglob("*"):
        if f.is_file():
            try:
                t += f.stat().st_size
            except OSError:
                pass
    return t


def main() -> int:
    freed = 0
    # 1) 整目录删除
    for rel in [".playwright-cli", "tools/__pycache__", "web/atlas"]:
        p = ROOT / rel
        if p.exists():
            s = size_of(p)
            shutil.rmtree(p, ignore_errors=True)
            freed += s
            print("  rmtree %-22s %8.1f MB" % (rel, s / 1048576))
    # 2) out/ 过程截图
    out = ROOT / "out"
    n = 0
    for f in sorted(out.glob("*.png")):
        if f.name in KEEP_OUT_PNG:
            continue
        freed += f.stat().st_size
        f.unlink()
        n += 1
    if n:
        print("  unlink out/*.png          %8d files" % n)
    # 3) 一次性脚本与临时记录
    for rel in ["ref/_tile_fmt_out.txt", "ref/scan_bundles.py", "ref/export_atlas.py",
                "ref/find_iter_refs.py", "ref/dig.py"]:
        p = ROOT / rel
        if p.exists():
            freed += p.stat().st_size
            p.unlink()
            print("  unlink %s" % rel)
    total = size_of(ROOT)
    print("[done] freed %.1f MB, workspace now %.1f MB" % (freed / 1048576, total / 1048576))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
