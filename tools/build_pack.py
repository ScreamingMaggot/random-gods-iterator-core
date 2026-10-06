"""打包渲染器唯一数据源 out/pack.json：音频逐帧通道 + 分幕 + 真实舱室图 + palette23 渐变。

原则：渲染器只读这一个对象，不在 HTML 里留第二处真相。
只保留在幕级或帧级确实携带信息的通道；已判定为死通道的（2-6kHz 通量）不进包。
坐标一律归一到 [0,1]（x 右正、y 上正），渲染器再乘视口，避免两套坐标。
"""
from __future__ import annotations

import base64
import io
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "pack.json"
FPS = 30.0
GRID = 15.0
CELLS = (int(384 // GRID) + 1, int(216 // GRID) + 1)     # 游戏的 floor(W/15)+1 约定 -> 26x15

# 保留的逐帧通道：幕级或帧级确有信息
CHANNELS = ["rms", "hi", "lowhigh", "flat", "tension", "onset", "pulse",
            "kick", "grit", "bass", "bass_on", "voice", "voice_on", "pc"]

# ElectricPower 曲线：全片唯一门控量（源码里 visible = Random < room.ElectricPower）
POWER_KEYS = ["boot", "spread", "chorus", "shift", "load", "peak", "glitch", "drain", "hold", "blackout", "silence"]
POWER = {"boot": 0.18, "spread": 0.55, "chorus": 0.92, "shift": 0.80, "load": 0.95,
         "peak": 1.00, "glitch": 0.97, "drain": 0.62, "hold": 0.70, "blackout": 0.0, "silence": 0.0}


def palette_ramps() -> list:
    a = np.asarray(Image.open(ROOT / "ref" / "palettes" / "palette23.png").convert("RGB"))
    return [[("#%02x%02x%02x" % tuple(int(v) for v in px)) for px in row] for row in a]


def main() -> int:
    f = json.loads((ROOT / "out" / "features.json").read_text(encoding="utf-8"))
    acts = json.loads((ROOT / "out" / "acts.json").read_text(encoding="utf-8"))
    nav = json.loads((ROOT / "ref" / "nav_map.json").read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "out" / "nav_audit.json").read_text(encoding="utf-8"))
    T = f["nframes"]

    ch = {}
    for k in CHANNELS:
        v = np.asarray(f[k])
        assert len(v) == T, (k, len(v))
        ch[k] = base64.b64encode(v.astype(np.uint8)).decode("ascii")
    bands = np.frombuffer(base64.b64decode(f["bands_b64"]), np.uint8)
    assert bands.size == f["nbands"] * T

    # --- 房间：nav_map.json 已给归一化矩形（x 右正、y 上正），直接沿用，不再二次归一 ---
    rooms = nav["rooms"]
    sub = {}
    out_rooms = {}
    for rid, r in rooms.items():
        s = r.get("subregion", "Five Pebbles")
        si = sub.setdefault(s, len(sub))
        rx0, rx1 = sorted((r["x0"], r["x1"]))
        ry0, ry1 = sorted((r["y0"], r["y1"]))
        out_rooms[rid] = {
            "rect": [round(rx0, 5), round(ry0, 5), round(rx1, 5), round(ry1, 5)],
            "c": [round((rx0 + rx1) / 2, 5), round((ry0 + ry1) / 2, 5)],
            "sub": si,
            "life": audit["score"].get(rid, 0.0),
            "violet": audit["violet_only"].get(rid, 0.0),
        }
    # 逐房间蓝紫/对象计数（绝对值，供"活簇"判定）
    lit = {}
    for p in sorted((ROOT / "ref" / "ss_tiles").glob("*.png")):
        m = re.match(r"ss_([a-z]+\d+)", p.name)
        if not m:
            continue
        k = "SS_" + m.group(1).upper()
        a = np.asarray(Image.open(p).convert("RGB"), np.int16)
        r_, g_, b_ = a[..., 0], a[..., 1], a[..., 2]
        lit[k] = max(lit.get(k, 0.0), float((((b_ > 120) & (r_ > 20) & (r_ < 190) & (g_ < 90)) |
                                            ((b_ > 120) & (r_ <= 40) & (g_ < 90))).mean()))
    obj = {}
    for p in sorted((ROOT / "ref" / "ss_rooms").glob("*_settings.txt")):
        m = re.match(r"ss_([a-z0-9]+)_settings", p.name)
        if not m:
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        obj["SS_" + m.group(1).upper()] = {
            w: len(re.findall(r"\b" + w + r"\b", t, re.I))
            for w in ("CoralCircuit", "CoralNeuron", "CorruptionTube", "SuperStructureFuses")}
    for rid, r in out_rooms.items():
        o = obj.get(rid, {})
        r["circuit"] = o.get("CoralCircuit", 0)
        r["neuron"] = o.get("CoralNeuron", 0)
        r["spores"] = o.get("CorruptionTube", 0)
        r["fuses"] = o.get("SuperStructureFuses", 0)
        r["painted"] = round(lit.get(rid, 0.0), 4)
        # 活簇判定用复合生命度（涂色 + 珊瑚回路 + 神经元 - 熔断器），
        # 不用"涂了蓝紫 或 放了回路"的 OR：那会把 E07(BUS，9 个神经元、0 蓝紫)误判成死。
        r["alive"] = bool(r["life"] >= 0.10)

    chambers = [{"code": c["code"], "name": c["name"], "room": c["room"],
                 "c": out_rooms.get(c["room"], {}).get("c"),
                 "rank": audit["anchors"].get(c["code"], {}).get("rank"),
                 "alive": out_rooms.get(c["room"], {}).get("alive", False)}
                for c in nav["chambers"]]
    corridors = [{"from": e["from"], "to": e["to"], "hops": e["hops"],
                  "units": e["units"], "path": e["path"]} for e in audit["corridors"]]

    # --- ElectricPower 时间曲线：每幕内从本幕值线性过渡到下一幕值 ---
    A = acts["acts"]
    pw = np.ones(T, np.float32) * POWER.get(A[-1]["role"], 0.5)
    for i, a in enumerate(A):
        i0 = min(int(a["start"] * FPS), T - 1)
        i1 = min(int(a["end"] * FPS), T)
        tgt = POWER.get(a["role"], 0.5)
        nxt = POWER.get(A[i + 1]["role"], tgt) if i + 1 < len(A) else tgt
        pw[i0:i1] = np.linspace(tgt, nxt, max(1, i1 - i0), dtype=np.float32)
    pw[:int(2.25 * FPS)] = np.linspace(0.02, POWER["boot"], int(2.25 * FPS), dtype=np.float32)
    pw[int(acts["events"]["power_off"] * FPS):] = 0.0

    pack = {
        "audio": {"fps": FPS, "nframes": T, "duration": f["duration"], "channels": ch,
                  "bands": base64.b64encode(bands).decode("ascii"), "nbands": f["nbands"],
                  "beats": f["beats"], "tempo": f["tempo"], "beat_period_s": f["beat_period_s"],
                  "second_clock_bpm": f["rhythm"]["lowband_competing_bpm"],
                  "rhythm": f["rhythm"], "key": f["key"], "mood": f["mood"],
                  "energy_share": f["meta"]["energy_share_by_band"]},
        "acts": A, "events": acts["events"],
        "power_curve_b64": base64.b64encode(np.clip(pw * 255, 0, 255).astype(np.uint8)).decode("ascii"),
        "map": {"bounds_game": nav["bounds"], "coord": "归一化 0-1，x 右正 y 上正（沿用 nav_map.json）",
                "subregions": [k for k, _ in sorted(sub.items(), key=lambda z: z[1])],
                "rooms": out_rooms, "chambers": chambers, "corridors": corridors,
                "hubs": audit["hubs"][:10], "alive_count": sum(1 for r in out_rooms.values() if r["alive"]),
                "connections": [[a, bb] for a, bb in nav["connections"] if a in out_rooms and bb in out_rooms]},
        "palette": {"ramps": palette_ramps(), "grid": GRID, "cells": CELLS,
                    "internal": [384, 216],
                    "ramp_roles": {"structure": 2, "structure_mid": 3, "shadow": 5, "base": 6,
                                   "hue_cycle": 1, "highlight": 0},
                    "rules": ["饱和红不在 palette23 内：红=活体对象层，可跳出青绿底",
                              "纯白 255 不参与 bloom（LightBloom.IsLevelLit: red>90 && red<255）",
                              "辉光有效带约亮度 180-254"]},
        "engine": {"glyph_grid": [95, 55], "grid_wrap_shift": 2,
                   "fire_chance_pow": 3, "lightup_decay": 0.9,
                   "disconnect_inverse_lerp": [300, 1600], "bloom_coef": 0.88},
    }
    OUT.parent.mkdir(exist_ok=True)
    # ensure_ascii=False 保留中文，但必须显式 utf-8：Windows 默认 GBK 会把中文写成 GBK 字节，
    # 产出一个"结构是 JSON、字符串值是 GBK"的坏档（浏览器按 UTF-8 读会成乱码）
    OUT.write_text(json.dumps(pack, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print("[ok] %s  %.1f KB" % (OUT.name, OUT.stat().st_size / 1024))
    print("     房间 %d，活簇 %d，子区域 %d，走廊 %d 条"
          % (len(out_rooms), pack["map"]["alive_count"], len(sub), len(corridors)))
    print("     网格 %dx%d 格（384x216 / 15px，floor+1 约定）" % CELLS)
    print("     ElectricPower: " + " ".join("%s %.2f" % (a["role"], POWER.get(a["role"], 0.5)) for a in A))
    print("     8 挂点: " + " ".join("%s@%s(%s,alive=%s)" % (c["code"], c["room"].replace("SS_", ""),
          ("排%s" % c["rank"]), c["alive"]) for c in chambers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
