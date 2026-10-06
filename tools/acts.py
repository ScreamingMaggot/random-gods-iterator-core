"""分幕校核：把用户主观听感的分段与数据独立切分（DP）+ 事件检测三方对照，产出 out/acts.json。

三方：
  A. 用户听感分段（USER，人工）
  B. DP 精确动态规划分段（不受主观影响，特征 = rms/亮度/平坦度/紧张度/色度，2Hz 池化）
  C. 事件检测（熄灯点、静默点、音符级最大跳变）
校核内容：
  - 复算用户表里点名的每个客观量，标出对得上 / 对不上 / 方向相反
  - 合并三方得到最终分幕，写 out/acts.json 供渲染器消费
注意：features.json 的 `air` 通道已废弃（2-6kHz 通量归一化后全曲饱和在 0.39-0.44，
      不携带段落信息）；用户口中的 "air" 实测对应 `hi`（1.5kHz 以上频带能量均值）。
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

import numpy as np
import librosa
from scipy.ndimage import uniform_filter1d

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
FEAT = ROOT / "out" / "features.json"
ACTS = ROOT / "out" / "acts.json"
MP3 = ROOT / "resource" / "Random Gods (Theme III) - James Primate.mp3"
FPS = 30.0

# 用户给出的分段（秒，判读）
USER = [(0.0, 2.25, "启动"), (2.25, 22.0, "阵列低速展开，单声部停滞"),
        (22.0, 39.0, "旋律进入，阵列第一次成群"), (39.0, 62.0, "织体换层，无旋律，管线增生"),
        (62.0, 88.0, "投影阵列满载"), (88.0, 113.0, "核心舱矩阵运算峰值"),
        (113.0, 146.0, "噪声/乱码涌现"), (146.0, 186.0, "承接段，阵列稳定空转"),
        (186.0, 193.1, "卸载/熄灯"), (193.1, 199.3, "静默")]

# 待核对断言：(描述, 用户值, 取哪个实测键)
# 待核对断言：(描述, 窗口, 实测键, 用户数值, 容差)。判定由代码算，不手写。
CLAIMS = [
    ("air 0.07->0.21", (2.25, 22.0), "hi_raw_lo_hi", [0.07, 0.21], 0.04),
    ("air 0.21->0.29", (22.0, 39.0), "hi_raw_lo_hi", [0.21, 0.29], 0.04),
    ("air 掉回 0.10", (39.0, 62.0), "hi_raw_mean", 0.10, 0.03),
    ("亮度 0.44", (39.0, 62.0), "bright_mean", 0.44, 0.03),
    ("tension 0.35", (39.0, 62.0), "tension_mean", 0.35, 0.05),
    ("亮度 0.50", (62.0, 88.0), "bright_mean", 0.50, 0.03),
    ("air 0.18", (62.0, 88.0), "hi_raw_mean", 0.18, 0.03),
    ("flat 0.06", (88.0, 113.0), "flat_mean", 0.06, 0.01),
    ("主声部 7 次跳变 (22-39s)", (22.0, 39.0), "voice_jumps", 7, 1),
    ("同样 7 次是否在 88-113s", (88.0, 113.0), "voice_jumps", 7, 1),
    ("flat 0.117", (113.0, 146.0), "flat_mean", 0.117, 0.01),
    ("air 0.218", (113.0, 146.0), "hi_raw_mean", 0.218, 0.03),
    ("rms 0.81 恒定", (146.0, 186.0), "rms_mean", 0.81, 0.03),
    ("bass_on=0", (146.0, 186.0), "bass_on", 0.0, 0.05),
    ("air 0.09->0.18", (146.0, 186.0), "hi_raw_lo_hi", [0.09, 0.18], 0.04),
    ("rms 0.517", (186.0, 193.1), "rms_mean", 0.517, 0.05),
    ("rms<0.05 且 6.2s", (193.1, 199.3), "tail_rms_dur", [0.05, 6.2], 0.4),
    ("86s 处 10.4 半音最大跳变", (0.0, 199.3), "global_max_jump", [86.0, 10.4], 2.0),
]



def dp_segment(F, nseg, min_len):
    n = F.shape[1]
    c1 = np.concatenate([np.zeros((F.shape[0], 1)), F.cumsum(1)], axis=1)
    c2 = np.concatenate([np.zeros((F.shape[0], 1)), (F ** 2).cumsum(1)], axis=1)
    INF = 1e18
    D = np.full((nseg + 1, n + 1), INF)
    P = np.zeros((nseg + 1, n + 1), int)
    D[0, 0] = 0.0
    for k in range(1, nseg + 1):
        for j in range(k * min_len, n + 1):
            i = np.arange((k - 1) * min_len, j - min_len + 1)
            if len(i) == 0:
                continue
            L = np.maximum(1, j - i).astype(float)
            s = c1[:, j][:, None] - c1[:, i]
            q = c2[:, j][:, None] - c2[:, i]
            tot = D[k - 1, i] + (q - s * s / L).sum(0)
            b = int(np.argmin(tot))
            D[k, j], P[k, j] = float(tot[b]), int(i[b])
    bnds, j = [n], n
    for k in range(nseg, 0, -1):
        j = int(P[k, j])
        bnds.append(j)
    return sorted(bnds), float(D[nseg, n])


def note_jumps(midi, ok, s, e, fps, gap=0.25):
    """音符级跳变：连续 voiced 帧压成音符（>=gap 秒，取中位音高），再数相邻音符半音跨度。

    直接用逐帧差会数到上百次"跳变"——那是跟踪抖动，不是音乐事件。
    """
    i0, i1 = int(s * fps), int(e * fps)
    notes = []
    i = i0
    while i < i1:
        if not ok[i]:
            i += 1
            continue
        j = i
        while j + 1 < i1 and ok[j + 1] and abs(midi[j + 1] - midi[j]) < 1.5:
            j += 1
        if (j - i + 1) / fps >= gap:
            notes.append((i / fps, float(np.median(midi[i:j + 1]))))
        i = j + 1
    jumps = [(round(notes[k + 1][0], 1), round(notes[k + 1][1] - notes[k][1], 1)) for k in range(len(notes) - 1)]
    big = [z for z in jumps if abs(z[1]) >= 3.0]
    return len(notes), len(jumps), big   # 音符数, 相邻转换数, 其中>=3半音者


def main() -> int:
    f = json.loads(FEAT.read_text(encoding="utf-8"))
    T, dur = f["nframes"], f["duration"]
    A = lambda k: np.asarray(f[k], float) / 255.0
    rms, hi, bl, ten, flat = A("rms"), A("hi"), A("lowhigh"), A("tension"), A("flat")
    bands = np.frombuffer(base64.b64decode(f["bands_b64"]), np.uint8).reshape(f["nbands"], T) / 255.0
    edges = np.array(f["meta"]["band_edges_hz"])[:-1]
    hi_raw = bands[edges >= 4000.0].mean(0)           # 未归一化：与用户表里的 air 同量纲
    bass_on, voice_on = np.asarray(f["bass_on"]) > 0.5, np.asarray(f["voice_on"]) > 0.5
    bass_m, voice_m = A("bass") * 30.0 + 28.0, A("voice") * 48.0

    def stats(s, e):
        i0 = min(int(s * FPS), T - 1)
        i1 = min(max(int(e * FPS), i0 + 1), T)
        L = max(1, (i1 - i0) // 8)
        vn, vj, vbig = note_jumps(voice_m, voice_on, s, e, FPS)
        bn_, bj_, bb_ = note_jumps(bass_m, bass_on, s, e, FPS)
        gvn, gvj, gvbig = note_jumps(voice_m, voice_on, 0.0, 192.0, FPS)   # 排除 192s 后的塌陷与静音
        gm = max(gvbig, key=lambda z: abs(z[1])) if gvbig else [0.0, 0.0]
        m = i0 + int(np.argmax(np.abs(np.diff(voice_m[i0:i1])))) + 1 if i1 - i0 > 2 else i0
        mid = int((s + e) / 2 * FPS)
        return {"rms_mean": round(float(rms[i0:i1].mean()), 3), "rms_std": round(float(rms[i0:i1].std()), 3),
                "hi_mean": round(float(hi[i0:i1].mean()), 3),
                "hi_raw_mean": round(float(hi_raw[i0:i1].mean()), 3),
                "hi_raw_lo_hi": [round(float(hi_raw[i0:i0 + L].mean()), 2), round(float(hi_raw[i1 - L:i1].mean()), 2)],
                "tail": [round(float(rms[i0:i1].mean()), 3), round(float(flat[i0:i1].max()), 3), round((i1 - i0) / FPS, 1)],
                "hi_lo_hi": [round(float(hi[i0:i0 + L].mean()), 2), round(float(hi[i1 - L:i1].mean()), 2)],
                "bright_mean": round(float(bl[i0:i1].mean()), 3),
                "tension_mean": round(float(ten[i0:i1].mean()), 3),
                "flat_mean": round(float(flat[i0:i1].mean()), 3),
                "bass_on": round(float(bass_on[i0:i1].mean()), 3),
                "bass_on_split": [round(float(bass_on[i0:mid].mean()), 2), round(float(bass_on[mid:i1].mean()), 2)],
                "voice_notes": vn, "voice_jumps": vj, "voice_big": vbig, "voice_big_n": len(vbig),
                "bass_notes": bn_, "bass_big": bb_,
                "max_jump": [round(m / FPS, 1), round(float(np.max(np.abs(np.diff(voice_m[i0:i1])))) if i1 - i0 > 2 else 0, 1)],
                "global_max_jump": [gm[0], gm[1]], "global_note_jumps_ge3st": gvj}

    print("=== 逐条断言校核（判定由实测自动给出，容差见 CLAIMS）===")
    verdicts, nok = [], 0
    for desc, (s, e), key, want, tol in CLAIMS:
        st = stats(s, e)
        got = st.get(key)
        if got is None:
            got = st["tail"][0] if key == "tail_rms_dur" else None
        if key == "tail_rms_dur":
            got = [st["tail"][0], st["tail"][2]]
        if key == "global_max_jump":
            got = st["global_max_jump"]
        if isinstance(got, (int, float)) and isinstance(want, (int, float)):
            d = abs(got - want)
            hit = d <= tol
        elif isinstance(got, list):
            d = [round(abs(float(x) - float(w)), 3) for x, w in zip(got, want)]
            hit = all(dd <= tol for dd in d)
        else:
            d, hit = None, False
        nok += int(hit)
        print("  %s %-30s 用户 %-16s 实测 %-18s 差 %s" % ("✓" if hit else "✗", desc, str(want), str(got), str(d)))
        verdicts.append({"claim": desc, "window": [s, e], "user": want, "measured": got, "diff": d, "match": bool(hit)})
    print("   自动判定：%d/%d 条吻合（容差见 CLAIMS）" % (nok, len(CLAIMS)))

    # --- 事件检测 ---
    body = rms[:int(192 * FPS)]
    lvl = float(np.median(body))
    i_collapse = int(np.argmax(rms[int(185 * FPS):] < 0.5 * lvl)) + int(185 * FPS) if (rms[int(185 * FPS):] < 0.5 * lvl).any() else T
    tail = rms[int(185 * FPS):]
    nz = np.nonzero(tail < 0.02)[0]
    i_silence = int(nz[0]) + int(185 * FPS) if len(nz) else T
    gvn, gvj, gvbig = note_jumps(voice_m, voice_on, 0, dur, FPS)
    events = {
        "power_off": round(i_collapse / FPS, 2),
        "silence_onset": round(i_silence / FPS, 2),
        "tail_decay_s": round((i_silence - i_collapse) / FPS, 2),
        "body_level": round(lvl, 3),
        "max_voice_jump": max(gvbig, key=lambda z: abs(z[1])) if gvbig else None,
        "all_voice_jumps_ge3st": gvbig,
        "voice_note_transitions": gvj,
        "voice_jumps_ge3st": len(gvbig),
        "note": "熄灯不是 186s：186-191.7s 仍满功率，实际塌陷在 %.1fs，混响尾巴拖到 %.1fs" % (i_collapse / FPS, i_silence / FPS),
    }
    print("\n=== 事件检测 ===")
    for k, v in events.items():
        print("   %-22s %s" % (k, v))

    # --- DP 独立分段 ---
    y, sr = librosa.load(str(MP3), sr=22050, mono=True)
    hop = int(round(sr / FPS))
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    C = librosa.feature.chroma_stft(S=S ** 2, sr=sr, hop_length=hop, n_fft=2048, tuning=0.0)
    nzf = lambda a: (a - a.min()) / (np.ptp(a) + 1e-12)
    Fe = np.vstack([nzf(rms[:T]), nzf(bl), nzf(flat), nzf(ten), C[:, :T]])
    pool = 15
    n = (Fe.shape[1] // pool) * pool
    Fp = uniform_filter1d(Fe[:, :n].reshape(Fe.shape[0], -1, pool).mean(2), 3, axis=1)
    dp = {}
    print("\n=== DP 独立分段（2Hz，最小段 10s）===")
    for k in (6, 8, 10, 12):
        b, c = dp_segment(Fp, k, 20)
        dp[k] = [round(i * pool / FPS, 1) for i in b]
        print("   nseg=%2d cost %7.2f -> %s" % (k, c, dp[k][1:-1]))
    ref = dp[10]
    print("\n=== 用户边界 vs DP(nseg=10) ===")
    match = []
    for a_, b_, lab in USER[1:]:
        r = min(ref, key=lambda z: abs(a_ - z))
        d = abs(a_ - r)
        match.append(round(d, 1))
        print("   %6.1fs (%-14s) -> DP %6.1fs  差 %4.1fs %s" % (a_, lab[:14], r, d, "✓" if d <= 3 else "✗"))
    print("   一致 %d/%d" % (sum(1 for d in match if d <= 3), len(match)))

    # --- 最终分幕：用户分段 + 事件校正（熄灯点、146-186 拆分） ---
    final = [
        (0.0, 2.25, "boot", "启动：阵列上电，单声部"),
        (2.25, 22.0, "spread", "低速展开：高频缓慢上升，旋律未入"),
        (22.0, 39.0, "chorus", "成群：紧张度骤降 0.40->0.19，主声部成形"),
        (39.0, 62.0, "shift", "换层：紧张度回到 0.40，高频回落，管线增生"),
        (62.0, 88.0, "load", "满载：亮度/高频同步抬升，投影阵列铺开"),
        (88.0, 113.0, "peak", "运算峰值：主声部 7 次 >=3 半音跳变集中在此"),
        (113.0, 146.0, "glitch", "乱码涌现：flat 0.12 为全曲最高，bass_on 掉到 0.09"),
        (146.0, 160.0, "drain", "抽稀：低音缺席(bass_on 0.00)，高频 0.20->0.09 持续衰减"),
        (160.0, events["power_off"], "hold", "空转承接：低音 160s 后重新接管至 0.95，rms 恒 0.82"),
        (events["power_off"], events["silence_onset"], "blackout", "熄灯：混响尾，非新乐段"),
        (events["silence_onset"], dur, "silence", "数字静音（flatness=1.0 为伪值）"),
    ]
    acts = []
    for s, e, role, note in final:
        st = stats(s, e)
        acts.append({"start": round(s, 2), "end": round(e, 2), "role": role, "note": note, **st})
    out = {"duration": dur, "fps": FPS, "acts": acts, "events": events,
           "claim_audit": verdicts,
           "user_boundaries_vs_dp": {"agree": sum(1 for d in match if d <= 3), "of": len(match), "dp_nseg10": dp[10]},
           "rhythm": f["rhythm"], "key": f["key"], "energy_share": f["meta"]["energy_share_by_band"]}
    ACTS.write_text(json.dumps(out, separators=(",", ":"), default=str))
    print("\n=== 最终分幕 -> %s ===" % ACTS.name)
    for x in acts:
        print("   %6.2f-%6.2f %-9s rms %.2f hi %.2f%s bright %.2f ten %.2f flat %.3f bass_on %.2f"
              % (x["start"], x["end"], x["role"], x["rms_mean"], x["hi_mean"],
                 str(x["hi_lo_hi"]), x["bright_mean"], x["tension_mean"], x["flat_mean"], x["bass_on"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
