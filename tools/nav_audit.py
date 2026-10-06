"""挂点与通信拓扑校核：用两组独立生命信号重排 70 房间，并用真实门图重算舱室间走廊。

背景：nav_map.md 给的 8 舱室挂点里 CLK/MUL/OUT/BUS/RX 五处落在无蓝紫的房间；
     而 SCENE_NOTES §9 称通信拓扑"与官方连接图一致"，实测 9 条边只有 2 条是真门直连。
本脚本做三件事：
  1. 复合生命度 = 图块蓝紫占比(画出来的珊瑚电路) + settings 里的 CoralCircuit/CoralNeuron/
     CorruptionTube 计数(放上去的活体对象) - SuperStructureFuses(熔断器)。
     两组信号不完全一致，所以同时给出各自排名与复合排名，供人工挑挂点。
  2. 对 8 个功能角色，在各自主责子区域内挑生命度最高的候选房间。
  3. 用真实门图 BFS 求 8 舱室之间的最短走廊（跳数 + 经过的房间），
     作为渲染器里"通信拓扑"的边——线要沿真实房间走，不能凭空连。
输出 out/nav_audit.json。
"""
from __future__ import annotations

import io
import json
import re
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "ref"
OUT = ROOT / "out" / "nav_audit.json"
LIVE_KEYS = ("CoralCircuit", "CoralNeuron", "CorruptionTube", "WallMycelia")


def room_violet() -> dict:
    """图块里蓝紫（画出来的活体电路）占比，取该房间所有图块的最大值。"""
    lit = {}
    for p in sorted(REF.glob("ss_tiles/*.png")):
        m = re.match(r"ss_([a-z]+\d+)", p.name)
        if not m:
            continue
        k = "SS_" + m.group(1).upper()
        a = np.asarray(Image.open(p).convert("RGB"), np.int16)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        v = float((((b > 120) & (r > 20) & (r < 190) & (g < 90)) | ((b > 120) & (r <= 40) & (g < 90))).mean())
        lit[k] = max(lit.get(k, 0.0), v)
    return lit


def room_objects() -> dict:
    out = {}
    for p in sorted(REF.glob("ss_rooms/*_settings.txt")):
        m = re.match(r"ss_([a-z0-9]+)_settings", p.name)
        if not m:
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        out["SS_" + m.group(1).upper()] = {w: len(re.findall(r"\b" + w + r"\b", t, re.I)) for w in LIVE_KEYS} \
            | {"SuperStructureFuses": len(re.findall(r"SuperStructureFuses", t, re.I))}
    return out


def main() -> int:
    N = json.loads((REF / "nav_map.json").read_text(encoding="utf-8"))
    M = json.loads((REF / "ss_map.json").read_text(encoding="utf-8"))
    rooms, G = M["rooms"], M["roomgraph"]
    lit, obj = room_violet(), room_objects()

    def norm(d, k):
        vs = np.array([d.get(r, {}).get(k, 0.0) for r in rooms], float)
        mx = vs.max() + 1e-9
        return lambda r: d.get(r, {}).get(k, 0.0) / mx

    nv = lambda r: lit.get(r, 0.0) / (max(lit.values()) + 1e-9)
    nc = norm(obj, "CoralCircuit")
    nn = norm(obj, "CoralNeuron")
    nt = norm(obj, "CorruptionTube")
    nf = norm(obj, "SuperStructureFuses")
    score = {r: 0.34 * nv(r) + 0.30 * nc(r) + 0.22 * nn(r) + 0.09 * nt(r) - 0.25 * nf(r) for r in rooms}
    violet_only = {r: nv(r) for r in rooms}
    obj_only = {r: 0.55 * nc(r) + 0.40 * nn(r) + 0.15 * nt(r) - 0.30 * nf(r) for r in rooms}

    rk = lambda d: sorted(d, key=lambda r: -d[r])
    top_s, top_v, top_o = rk(score), rk(violet_only), rk(obj_only)
    print("=== 三种排名的前 15 名（复合 / 仅图块蓝紫 / 仅放置物）===")
    print("%-4s %-12s %8s | %-12s %8s | %-12s %8s" % ("#", "复合", "分", "蓝紫", "分", "对象", "分"))
    for i in range(15):
        print("%-4d %-12s %8.3f | %-12s %8.3f | %-12s %8.3f" % (
            i + 1, top_s[i], score[top_s[i]], top_v[i], violet_only[top_v[i]], top_o[i], obj_only[top_o[i]]))
    ov = len(set(top_s[:21]) & set(top_v[:21]))
    oo = len(set(top_s[:21]) & set(top_o[:21]))
    print("\n前 21 名重合度：复合∩蓝紫 %d/21，复合∩对象 %d/21 -> 两组信号在'谁活着'上并不完全同意" % (ov, oo))

    print("\n=== 现有 8 挂点在复合排名中的位置 ===")
    pos = {r: i + 1 for i, r in enumerate(top_s)}
    for c in N["chambers"]:
        r = c["room"]
        print("   %-4s %-8s %-12s 复合 %+.3f 排 %2d/%d   蓝紫 %.3f  Circuit %d Neuron %d 熔断 %d"
              % (c["code"], c["name"], r, score[r], pos[r], len(rooms), nv(r),
                 obj.get(r, {}).get("CoralCircuit", 0), obj.get(r, {}).get("CoralNeuron", 0),
                 obj.get(r, {}).get("SuperStructureFuses", 0)))

    # 每个角色的更优候选要按子区域与空间距离单独定，不做全局 top-N（全局 top-N 对每个角色
    # 都印同一批房间，是废信息，第一版就是这么错的）。这里只报现挂点的排名。

    # --- 真实走廊 ---
    adj = {k: [e["to"] for e in G.get(k, [])] for k in G}

    def bfs(a, b):
        if a == b:
            return [a]
        q, seen = deque([(a, [a])]), {a}
        while q:
            c, path = q.popleft()
            for n in adj.get(c, []):
                if n in seen or n not in rooms:
                    continue
                seen.add(n)
                if n == b:
                    return path + [n]
                q.append((n, path + [n]))
        return None

    by = {c["code"]: c["room"] for c in N["chambers"]}
    cx = lambda r: (rooms[r]["cx"], rooms[r]["cy"])

    def path_len(p):
        return float(sum(np.hypot(cx(p[i + 1])[0] - cx(p[i])[0], cx(p[i + 1])[1] - cx(p[i])[1]) for i in range(len(p) - 1)))

    print("\n=== 舱室间真实走廊（原 9 条边逐条重算）===")
    edges = []
    for a, b in [("RX", "DEC"), ("RX", "CLK"), ("DEC", "MUL"), ("RF", "MUL"), ("MUL", "OUT"),
                 ("MUL", "WRB"), ("OUT", "BUS"), ("WRB", "BUS"), ("CLK", "BUS")]:
        p = bfs(by[a], by[b])
        hops = (len(p) - 1) if p else None
        direct = hops == 1
        L = path_len(p) if p else 0.0
        print("   %-4s->%-4s %s %2s 跳  走廊长 %6.0f 单位  %s" % (a, b, "真门直连✓" if direct else "需中转✗", hops, L,
              " → ".join(x.replace("SS_", "") for x in (p or []))))
        edges.append({"from": a, "to": b, "hops": hops, "direct": direct, "units": round(L, 1), "path": p})
    # 枢纽统计：哪些真实房间被多条走廊共用
    cnt = {}
    for e in edges:
        for x in (e["path"] or [])[1:-1]:
            cnt[x] = cnt.get(x, 0) + 1
    print("\n   被多条走廊共用的中转枢纽:", sorted(cnt.items(), key=lambda z: -z[1])[:8])
    OUT.write_text(json.dumps({
        "score": {r: round(score[r], 4) for r in rooms},
        "violet_only": {r: round(violet_only[r], 4) for r in rooms},
        "objects_only": {r: round(obj_only[r], 4) for r in rooms},
        "ranking_composite": top_s,
        "anchors": {c["code"]: {"room": c["room"], "rank": pos[c["room"]], "score": round(score[c["room"]], 4)}
                    for c in N["chambers"]},
        "corridors": edges,
        "hubs": sorted(cnt.items(), key=lambda z: -z[1]),
    }, separators=(",", ":"), ensure_ascii=False))
    print("\n[ok] ->", OUT.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
