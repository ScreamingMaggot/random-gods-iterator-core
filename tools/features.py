"""Random Gods (Theme III) — 频谱/节奏/旋律/情绪特征提取（纯器乐，无歌词）。

技术路径（本地 librosa/scipy，全部可复核）：
  STFT -> 48 段对数频带能量 -> RMS/通量/质心/rolloff/平坦度/低高比
  节拍：不用 librosa.beat 的默认回落，改在 [96,144] BPM 上暴力搜索 tempo+相位，
        以"网格点上的起始强度 / 随机相位基线"为得分 -> 自证的 BPM、小节线、下拍
  打击：按本曲真实能谱分带 kick(28-120) / punch(120-420) / grit(420-1600)；
        2k 以上在本曲几乎无能量，故不设 hat 通道（避免死通道），并回报各带能量占比
  鼓点模式：起始强度投影到 16 分音符网格 -> 模式向量 + 跨小节一致性 + 栅格外比例
  旋律：HPSS 和声轨 pyin 低音轮廓(55-260Hz, vprob>0.10) + 250-2000Hz 主声部谱峰
        -> 音符切分；色度轨迹 + 每段固定音型(ostinato)周期
  和声：色度 + Krumhansl-Schmuckler 调性 + 色度熵补作紧张度
  结构：自相似矩阵新颖度 -> 分段
输出 out/features.json（渲染器直接消费）+ out/verify_features.png。
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

import numpy as np
import librosa
from scipy.ndimage import median_filter, uniform_filter, uniform_filter1d
from scipy.signal import find_peaks

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
MP3 = ROOT / "resource" / "Random Gods (Theme III) - James Primate.mp3"
OUT = ROOT / "out" / "features.json"
PLOT = ROOT / "out" / "verify_features.png"

SR = 22050
FPS = 30.0
NBANDS = 48
NFFT = 2048
SUBDIV = 4
STEPS = 16
NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
KS_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
PERC = {"kick": (28, 120), "punch": (120, 420), "grit": (420, 1600)}
HI_CUT_HZ = 4000.0   # "空气感/高频细节"通道：4kHz 以上对数频带能量均值（与人工听感 air 最吻合的截止）


def norm_i(a, p=98):
    a = np.asarray(a, float)
    hi = np.percentile(a, p)
    if hi <= 1e-9:
        hi = a.max() + 1e-9
    return np.clip(a / hi, 0, 1)


def jsn(o):
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return str(o)


def band_flux(S, freqs, lo, hi):
    m = (freqs >= lo) & (freqs < hi)
    if not m.any():
        return np.zeros(S.shape[1])
    s = np.log(S[m, :] + 1e-10)
    d = np.diff(s, axis=1, prepend=s[:, :1])
    d[d < 0] = 0
    return d.sum(axis=0)


def tempo_lock(sig, fps, lo=55.0, hi=155.0, res=0.25, win_hz=0.07, band=(0.5, 3.5)):
    """尺度无关的节拍锁定度：起始强度功率谱落在候选拍频 ±win_hz 内的能量占比。

    不用"网格点均值/全局均值"，因为那个比值被起始信号的稀疏度污染
    （持续型音乐的 onset 中位数很高，比值会假性趋近 1）。
    随机相位下的期望占比 = 2*win_hz / band 宽度，实际值除以它即"锁定倍数"。
    对照（--selftest 合成节拍器 @120BPM）占比 ~0.68；本曲宽带 onset ~0.12 @119.5，
    即约 3 倍于随机 —— 拍点存在但不硬，属松锁定。
    """
    o = np.asarray(sig, float)
    o = o - o.mean()
    n = len(o)
    P = np.abs(np.fft.rfft(o * np.hanning(n))) ** 2
    fr = np.fft.rfftfreq(n, d=1.0 / fps)
    m = (fr >= band[0]) & (fr <= band[1])
    tot = float(P[m].sum()) + 1e-20
    nb = max(1, int(round(win_hz * n / fps)))
    out = []
    for bpm in np.arange(lo, hi + 1e-6, res):
        k = int(np.argmin(np.abs(fr - bpm / 60.0)))
        out.append((float(P[max(0, k - nb):k + nb].sum() / tot), float(bpm)))
    out.sort(reverse=True)
    return out, float(2 * win_hz / (band[1] - band[0]))


def fit_phase(onset, period, T, fps):
    """固定周期后搜相位：网格点上起始强度均值 / 全局均值。"""
    o = norm_i(onset)
    base = float(o.mean()) + 1e-9
    best = (-1.0, 0.0)
    for ph in np.arange(0.0, period, max(0.05, period / 200.0)):
        idx = np.arange(ph, T, period)
        if len(idx) < 4:
            continue
        i0 = np.floor(idx).astype(int)
        frac = idx - i0
        v = o[np.minimum(i0, T - 1)] * (1 - frac) + o[np.minimum(i0 + 1, T - 1)] * frac
        sc = float(v.mean()) / base
        if sc > best[0]:
            best = (sc, float(ph))
    return best


def refine_tempo(sig, fps, bpm0, win_hz=0.07):
    """粗峰附近用功率重心做亚分度细化。

    FFT 频率分辨率 = fps/n，换算成 BPM 即 60*fps/n：40s 的对照信号只能到 ±1.5 BPM，
    199s 的本曲能到 ±0.3 BPM。不细化就会把 120 认成 122（对照实验里实测到了这一步）。
    返回 (细化 BPM, 分辨率 BPM)。
    """
    o = np.asarray(sig, float)
    o = o - o.mean()
    n = len(o)
    res = 60.0 * fps / n
    P = np.abs(np.fft.rfft(o * np.hanning(n))) ** 2
    fr = np.fft.rfftfreq(n, d=1.0 / fps)
    m = (fr >= bpm0 / 60.0 - win_hz) & (fr <= bpm0 / 60.0 + win_hz)
    if not m.any() or P[m].sum() <= 0:
        return float(bpm0), res
    return float((fr[m] * P[m]).sum() / P[m].sum() * 60.0), res


def lock_perm_pvalue(onset, fps, lo=95.0, hi=150.0, n_perm=60, seed=0):
    """置换检验：把 onset 序列随机重排（破坏时间结构、保留幅值分布）后重算锁定度，
    得到"无节奏"零假设下最大锁定度的分布，用来判断实测峰值是否显著。

    这一步是必要的：FFT 在几百个候选 BPM 上取最大值本身会抬高假峰，
    只看"几倍于均匀分布"会把噪声里的假峰当成节奏。
    """
    rng = np.random.RandomState(seed)
    o = np.asarray(onset, float)
    obs, _ = tempo_lock(o, fps, lo, hi)
    obs_max = max(l for l, _ in obs)
    null = []
    for _ in range(n_perm):
        p = rng.permutation(o)
        lk, _ = tempo_lock(p, fps, lo, hi)
        null.append(max(l for l, _ in lk))
    null = np.array(null)
    p = float((np.sum(null >= obs_max) + 1) / (len(null) + 1))
    return obs_max, float(np.percentile(null, 95)), p, null


def downbeat(beat_frames, low_flux, T, nb=4):
    """在 4 个拍位中找能量最强者作为下拍（假定 4/4）。"""
    a = norm_i(low_flux)
    acc = np.zeros(nb)
    cnt = np.zeros(nb)
    for i, f in enumerate(beat_frames):
        j = int(round(f))
        if 0 <= j < T:
            acc[i % nb] += a[j]
            cnt[i % nb] += 1
    return int(np.argmax(acc / np.maximum(cnt, 1))), (acc / np.maximum(cnt, 1)).round(3).tolist()


def step_grid(period, phase, T):
    g = np.arange(phase, T + period, period)          # 拍
    sub = np.repeat(g, SUBDIV) + np.tile(np.arange(SUBDIV) * period / SUBDIV, len(g))
    sub = sub[sub < T]
    return g, sub


def drum_pattern(step_abs, kick, punch, grit, fps):
    """把离散打击事件（起始峰）投到 16 分网格 -> 模式向量 + 跨小节一致性。

    不能用连续 flux 逐帧累加：199s 的连续能量会把 16 个格子全部填满，
    得到一条平线（第一版实测就是这样，模式全在 0.02-0.25 之间无差别）。
    必须先检出离散事件峰，再按峰所落的格子累加峰幅。
    """
    s16 = step_abs % STEPS
    bar_of_frame = step_abs // STEPS
    nb = int(bar_of_frame.max()) + 1 if len(step_abs) else 1
    out, cons, nev = {}, {}, {}
    for name, v in (("kick", kick), ("punch", punch), ("grit", grit)):
        a = norm_i(v)
        pk, props = find_peaks(a, height=0.18, distance=max(1, int(0.06 * fps)))
        acc = np.zeros(STEPS)
        np.add.at(acc, s16[pk], a[pk])
        per = np.zeros((nb, STEPS))
        np.add.at(per, (bar_of_frame[pk], s16[pk]), a[pk])
        pn = per / (per.sum(1, keepdims=True) + 1e-9)
        c = [np.corrcoef(pn[i], pn.mean(0))[0, 1] for i in range(nb) if pn[i].std() > 1e-6]
        out[name] = [round(float(x), 3) for x in norm_i(acc, 100)]
        cons[name] = round(float(np.clip(np.mean(c), 0, 1)), 3) if c else 0.0
        nev[name] = int(len(pk))
    return out, cons, nb, nev


def main() -> int:
    assert MP3.exists(), MP3
    y, sr = librosa.load(str(MP3), sr=SR, mono=True)
    dur = float(len(y) / sr)
    hop = int(round(sr / FPS))
    S = np.abs(librosa.stft(y, n_fft=NFFT, hop_length=hop, window="hann"))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=NFFT)
    T = S.shape[1]
    times = librosa.frames_to_time(np.arange(T), sr=sr, hop_length=hop)

    # --- 48 对数频带 ---
    edges = np.geomspace(30.0, 8000.0, NBANDS + 1)
    db = librosa.amplitude_to_db(S, ref=np.max)
    bands = np.zeros((NBANDS, T), np.float32)
    for b in range(NBANDS):
        lo, hi = edges[b], edges[b + 1]
        sel = (freqs >= lo) & (freqs < hi)
        bands[b] = db[sel].mean(axis=0) if sel.any() else db[np.argmin(np.abs(freqs - np.sqrt(lo * hi)))]
    floor = np.percentile(bands, 3, axis=1, keepdims=True)
    bn = np.clip((bands - floor) / 80.0, 0, 1)

    # --- 逐帧描述子 ---
    rms = librosa.feature.rms(y=y, hop_length=hop)[0][:T]
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)[:T]
    cent = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0][:T]
    roll = librosa.feature.spectral_rolloff(y=y, sr=sr, hop_length=hop)[0][:T]
    flat = librosa.feature.spectral_flatness(y=y, hop_length=hop)[0][:T]
    # 谱通量：对"频带"轴求和得到逐帧量（axis=1 会误沿时间轴求和，只剩 48 个值）
    flux = np.concatenate([[0.0], np.maximum(0, np.diff(bn, axis=1)).sum(axis=0)])
    low_e, high_e = bn[0:10].sum(0), bn[-14:].sum(0)
    lowhigh = np.clip((high_e - low_e) / (low_e + high_e + 1e-9), -1, 1)

    # --- 能谱占比（分带依据，供审计） ---
    e2 = (S ** 2).sum(1)
    e2 = e2 / (e2.sum() + 1e-12)
    shares = {k: round(float(e2[(freqs >= lo) & (freqs < hi)].sum()), 4) for k, (lo, hi) in PERC.items()}
    shares["sub_20_60"] = round(float(e2[(freqs >= 20) & (freqs < 60)].sum()), 4)
    shares["top_above_2k"] = round(float(e2[freqs >= 2000].sum()), 4)
    # 高频细节用"频带能量均值"而不是"频带通量"：2-6kHz 通量归一化后全曲恒定在 0.39-0.44、
    # 每段峰值都顶到 1.00，是被 0.66% 能量喂出来的饱和噪声通道，不携带段落信息。
    hi_sel = edges[:-1] >= HI_CUT_HZ
    hi_band = bn[hi_sel].mean(0)

    # --- 打击分带（先算，节拍搜索与下拍都要用） ---
    pf = {k: band_flux(S, freqs, lo, hi) for k, (lo, hi) in PERC.items()}

    # --- 节拍：尺度无关锁定度搜索 + 定相 + 下拍 ---
    locks, chance = tempo_lock(onset, FPS)
    cand = [(lk, bp) for lk, bp in locks if 95.0 <= bp <= 150.0]
    lock, bpm_coarse = max(cand, key=lambda z: z[0])
    bpm, tres = refine_tempo(onset, FPS, bpm_coarse)
    obs_max, null95, pval, _null = lock_perm_pvalue(onset, FPS)
    period = FPS * 60.0 / bpm
    score, phase = fit_phase(onset, period, T, FPS)
    beat_frames, sub_frames = step_grid(period, phase, T)
    beat_times = [float(times[min(int(i), T - 1)]) for i in beat_frames if i < T]
    db_idx, db_weights = downbeat(beat_frames, pf["kick"] + pf["punch"], T)
    # 低频段是否有另一条独立调制线（本曲实测 ~142，与宽带 119.5 并存）
    lk_low, _ = tempo_lock(pf["kick"], FPS, 95.0, 165.0)
    low_lock, low_bpm = lk_low[0]
    decay = float(np.exp(-1.0 / (FPS * 0.16)))
    pulse = np.zeros(T, np.float32)
    bi = np.clip(np.round(beat_frames).astype(int), 0, T - 1)
    bi = bi[bi < T]
    imp = np.zeros(T)
    imp[bi] = 1.0
    for i in range(T):
        pulse[i] = 1.0 if imp[i] > 0 else (pulse[i - 1] * decay if i else 0.0)

    # --- 16 分模式量化 ---
    step_of_frame = np.clip(np.searchsorted(sub_frames, np.arange(T), side="right") - 1, 0, len(sub_frames) - 1)
    frac_in_step = (np.arange(T) - sub_frames[step_of_frame]) / max(1e-9, period / SUBDIV)
    pattern, cons, nbars, nev = drum_pattern(step_of_frame, pf["kick"], pf["punch"], pf["grit"], FPS)
    on = norm_i(pf["kick"] + pf["punch"] + pf["grit"])
    pk, _ = find_peaks(on, height=0.25, distance=2)
    offgrid = float(np.mean(np.abs(frac_in_step[pk] - np.round(frac_in_step[pk])) > 0.34)) if len(pk) else 0.0

    # --- HPSS：低音轮廓 + 主声部谱峰 ---
    H, P = librosa.effects.hpss(y)
    f0b, vpb = librosa.pyin(H, fmin=41.0, fmax=262.0, sr=sr, hop_length=hop)[:2]
    bass_ok = np.isfinite(f0b) & (vpb > 0.10)
    bass_midi = np.where(bass_ok, librosa.hz_to_midi(np.where(bass_ok, f0b, 110.0)), np.nan)
    filled = np.where(np.isfinite(bass_midi), bass_midi, np.nanmedian(bass_midi) if np.isfinite(bass_midi).any() else 45.0)
    bass_midi = median_filter(np.asarray(filled, float), size=5)
    bass_voiced = bass_ok

    # 主声部：250-2000Hz 内最强谱峰 -> midi，作为"可听旋律线"的近似
    sel = (freqs >= 250) & (freqs <= 2000)
    Sh = np.where(sel[:, None], S, 0.0)
    top_idx = np.argmax(Sh, axis=0)
    voice_hz = np.maximum(freqs[top_idx], 1.0)   # 静音帧 argmax 会落到 0Hz _bin
    voice_str = Sh[top_idx, np.arange(T)] / (S[:, np.arange(T)].max(0) + 1e-9)
    voice_midi = librosa.hz_to_midi(voice_hz)
    voice_ok = voice_str > 0.25

    # --- 音符切分（低音线 + 主声部） ---
    def segment(midi, ok, min_len=4):
        notes, i = [], 0
        while i < T:
            if not ok[i]:
                i += 1
                continue
            j = i
            while j + 1 < T and ok[j + 1] and abs(midi[j + 1] - midi[j]) < 1.2:
                j += 1
            if j - i + 1 >= min_len:
                seg = midi[i:j + 1]
                notes.append({"start": round(float(times[i]), 3), "end": round(float(times[j]), 3),
                              "midi": int(round(float(np.median(seg)))),
                              "name": NOTE[int(round(float(np.median(seg)))) % 12],
                              "oct": int(round(float(np.median(seg))) // 12 - 1)})
            i = j + 1
        return notes
    bass_notes = segment(bass_midi, bass_voiced)
    voice_notes = segment(voice_midi, voice_ok)

    # --- 色度 / 调性 / 紧张度 ---
    chr_ = librosa.feature.chroma_stft(S=S ** 2, sr=sr, hop_length=hop, n_fft=NFFT, tuning=0.0)[:, :T]
    cm = chr_.mean(1)
    cm = cm / (cm.sum() + 1e-9)
    best = max(((np.corrcoef(np.roll(cm, -t), p)[0, 1], t, m)
                for t in range(12) for m, p in (("major", KS_MAJ), ("minor", KS_MIN))), key=lambda z: z[0])
    key = {"name": NOTE[best[1]], "mode": best[2], "corr": round(float(best[0]), 3),
           "profile": [round(float(v), 3) for v in cm]}
    ent = -(chr_ * np.log(chr_ + 1e-9)).sum(0) / np.log(12)
    tension = np.clip(1.0 - norm_i(ent, 98), 0, 1)
    pc_traj = np.argmax(chr_, axis=0)          # 每帧主音级 -> 驱动色相身份

    # --- 结构分段 ---
    d = np.concatenate([bn.T, 3 * lowhigh[:, None], 4 * flat[:, None], 2 * tension[:, None]], axis=1)
    pool = max(1, int(round(FPS / 4.0)))
    n = (len(d) // pool) * pool
    D = d[:n].reshape(-1, pool, d.shape[1]).mean(1)
    Dn = (D - D.mean(1, keepdims=True)) / (np.linalg.norm(D, axis=1, keepdims=True) + 1e-9)
    Simg = Dn @ Dn.T
    w = 16
    B = uniform_filter(Simg, (w, w), mode="nearest")
    m = len(Simg)
    a = w // 2
    t = np.arange(a, m - a)
    nov = np.concatenate([[0.0] * a,
                          (B[t - a][:, t - a].diagonal() + B[t + a][:, t + a].diagonal()
                           - B[t - a][:, t + a].diagonal() - B[t + a][:, t - a].diagonal()) / 2,
                          [0.0] * (m - len(t) - a)])
    nov = uniform_filter1d(nov, 3)
    nov = nov / (nov.max() + 1e-12)
    pps = FPS / pool                       # 新颖度序列的采样率（步/秒），不是 4.0
    # 自适应阈值：先按 mean+0.6std 取峰，段数不足则逐级放宽；再合并过短段
    bnd_s = []
    for k in (0.6, 0.4, 0.25, 0.12):
        cand, _ = find_peaks(nov, distance=int(6.0 * pps), height=nov.mean() + k * nov.std())
        bnd_s = list(cand / pps)
        if len(bnd_s) + 1 >= 5:
            break
    bounds = np.concatenate([[0.0], np.asarray(bnd_s, float), [dur]])
    # 合并过短的段（<10s 并入相邻较弱的一段）
    while len(bounds) > 2:
        widths = np.diff(bounds)
        j = int(np.argmin(widths))
        if widths[j] >= 10.0:
            break
        keep = max(0, min(len(bounds) - 2, j if j == 0 else (j - 1 if widths[j - 1] > widths[min(j + 1, len(widths) - 1)] else j)))
        bounds = np.delete(bounds, keep + 1)
    sections = []
    for i in range(len(bounds) - 1):
        i0, i1 = int(bounds[i] * FPS), min(int(bounds[i + 1] * FPS), T)
        if i1 <= i0:
            continue
        seg = chr_[:, i0:i1].mean(1)
        seg = seg / (seg.sum() + 1e-9)
        # 固定音型周期：色度序列自相关在 2~32 拍区间内的最强峰
        # （从 lag=1 起找必然命中 lag1，自相关本就单调下降 —— 第一版即错在此）
        cs = chr_[:, i0:i1].T.astype(float)
        cs = cs - cs.mean(0, keepdims=True)
        lo = max(1, int(2.0 * 60.0 / bpm * FPS))
        hi = min(int(32.0 * 60.0 / bpm * FPS), len(cs) // 2)
        apk = 0
        if hi > lo:
            ac = np.array([np.mean(np.sum(cs[:-k] * cs[k:], axis=1)) for k in range(lo, hi)])
            ac = ac / (np.abs(ac).max() + 1e-12)
            if ac.max() > 0.30:
                apk = int(np.argmax(ac)) + lo
        sections.append({
            "start": round(float(bounds[i]), 2), "end": round(float(bounds[i + 1]), 2),
            "bars": round((bounds[i + 1] - bounds[i]) * 60.0 / bpm / 4.0, 1),
            "rms": round(float(np.mean(norm_i(rms)[i0:i1])), 3),
            "bright": round(float(np.mean(lowhigh[i0:i1])), 3),
            "noise": round(float(np.mean(flat[i0:i1])), 4),
            "cent": round(float(np.mean(cent[i0:i1])), 1),
            "onset_density": round(float(np.mean(norm_i(onset)[i0:i1])), 3),
            "tension": round(float(np.mean(tension[i0:i1])), 3),
            "bass_midi": round(float(np.median(bass_midi[i0:i1])), 1),
            "pc": NOTE[int(np.argmax(seg))],
            "ostinato_beats": round(apk / FPS * bpm / 60.0, 2) if apk else 0.0,
        })
    lv = np.sort([s["rms"] for s in sections])
    for s in sections:
        k = int(np.searchsorted(lv, s["rms"]) * 4 / max(1, len(sections)))
        s["role"] = ["低伏", "铺垫", "抬升", "顶点"][min(3, max(0, k))] + ("·明" if s["bright"] > 0 else "·暗")

    # --- 情绪量化 ---
    sl = slice(int(0.05 * T), int(0.95 * T))
    dyn = float(np.percentile(rms[sl], 90) - np.percentile(rms[sl], 10))
    mood = {
        "brightness_mean": round(float(np.mean(lowhigh[sl])), 3),
        "dynamic_range": round(dyn / (rms[sl].max() + 1e-9), 3),
        "flatness_mean": round(float(np.mean(flat[sl])), 4),
        "centroid_mean_hz": round(float(np.mean(cent[sl])), 1),
        "beat_rate_per_s": round(float(1.0 / (period / FPS)), 2),
        "grid_score": round(float(score), 3),
        "beat_lock": round(float(lock), 4),
        "beat_lock_x_chance": round(float(lock / chance), 2),
        "bass_voiced_share": round(float(np.mean(bass_voiced)), 3),
        "voice_ok_share": round(float(np.mean(voice_ok)), 3),
        "offgrid_ratio": round(offgrid, 3),
        "bar_regularity": round(float(np.mean([cons[k] for k in cons])), 3),
        "tension_mean": round(float(np.mean(tension[sl])), 3),
    }

    R = lambda a: np.clip(np.rint(np.nan_to_num(a) * 255), 0, 255).astype(np.uint8)
    feat = {
        "fps": FPS, "nframes": int(T), "nbands": NBANDS, "duration": dur,
        "meta": {"source": MP3.name, "sr": SR, "fps": FPS, "nframes": int(T), "nbands": NBANDS,
                 "duration": dur, "hop": hop, "extractor": "features.py (librosa/scipy)",
                 "band_edges_hz": [round(float(x), 1) for x in edges],
                 "percussion_bands_hz": {k: list(v) for k, v in PERC.items()},
                 "energy_share_by_band": shares,
                 "hi_channel": "hi = %.0fHz 以上对数频带能量均值（对应听感上的'空气感/高频细节'）" % HI_CUT_HZ,
                 "dead_channel_note": "2kHz 以上只占全曲能量 %.2f%%，hi 通道是相对量，不可当作绝对亮度使用" % (100 * shares["top_above_2k"])},
        "rhythm": {"bpm": round(float(bpm), 2),
                   "bpm_fft_resolution": round(float(tres), 3),
                   "beat_lock": round(float(lock), 4),
                   "lock_chance_uniform": round(chance, 4),
                   "lock_x_chance": round(float(lock / chance), 2),
                   "lock_null_p95": round(null95, 4),
                   "lock_perm_pvalue": round(pval, 4),
                   "grid_significant": bool(pval < 0.05),
                   "phase_align_ratio": round(float(score), 3),
                   "downbeat_index": db_idx,
                   "beat_position_weights": db_weights,
                   "lowband_competing_bpm": round(float(low_bpm), 2),
                   "lowband_competing_lock": round(float(low_lock), 4),
                   "top6_lock_candidates": [[round(b, 2), round(l, 4)] for l, b in locks[:6]],
                   "interpretation": "宽带拍点 %.1f BPM，锁定 %.4f（置换检验 p=%.3f，零假设 95%% 分位 %.4f）；"
                                     "低频另有 %.0f BPM 调制线，与宽带不重合 -> 节奏层松耦合，不宜做硬量化脉冲"
                                     % (bpm, lock, pval, null95, low_bpm)},
        "bands_b64": base64.b64encode(R(bn).tobytes()).decode("ascii"),
        "rms": R(norm_i(rms)).tolist(),
        "onset": R(norm_i(onset)).tolist(),
        "flux": R(norm_i(flux)).tolist(),
        "cent": R(norm_i(cent)).tolist(),
        "roll": R(norm_i(roll)).tolist(),
        "flat": R(norm_i(flat)).tolist(),
        "lowhigh": R((lowhigh + 1) / 2).tolist(),
        "tension": R(tension).tolist(),
        "pulse": R(norm_i(pulse, 99)).tolist(),
        "kick": R(norm_i(pf["kick"])).tolist(),
        "punch": R(norm_i(pf["punch"])).tolist(),
        "grit": R(norm_i(pf["grit"])).tolist(),
        "hi": R(norm_i(hi_band, 99)).tolist(),
        "bass": R(np.clip((bass_midi - 28) / 30.0, 0, 1)).tolist(),
        "bass_on": bass_voiced.astype(np.uint8).tolist(),
        "voice": R(norm_i((voice_midi - 48) / 48, 99)).tolist(),
        "voice_on": voice_ok.astype(np.uint8).tolist(),
        "pc": pc_traj.astype(np.uint8).tolist(),
        "beats": [round(b, 3) for b in beat_times],
        "tempo": round(float(bpm), 2),
        "beat_period_s": round(float(period / FPS), 4),
        "bar_period_s": round(float(period * 4 / FPS), 4),
        "downbeats": [round(float(times[min(int(i), T - 1)]), 3) for i in beat_frames[::4] if i < T],
        "drum_pattern": pattern,
        "drum_regularity": cons,
        "melody": {"bass_notes": len(bass_notes), "voice_notes": len(voice_notes),
                   "bass_range_midi": [int(np.nanmin(bass_midi)), int(np.nanmax(bass_midi))],
                   "bass_mean_midi": round(float(np.mean(bass_midi[bass_voiced])), 1) if bass_voiced.any() else 0.0,
                   "bass_step_mean_semitone": round(float(np.mean(np.abs(np.diff(bass_midi[bass_voiced])))), 2) if bass_voiced.sum() > 2 else 0.0,
                   "bass_density_per_s": round(len(bass_notes) / dur, 2),
                   "voice_range_midi": [float(voice_midi[voice_ok].min()), float(voice_midi[voice_ok].max())] if voice_ok.any() else [0, 0],
                   "voice_density_per_s": round(len(voice_notes) / dur, 2),
                   "bass_top": bass_notes[:24]},
        "key": key,
        "sections": sections,
        "structure": {"boundaries": [round(float(x), 2) for x in bounds],
                      "novelty": [round(float(v), 3) for v in nov]},
        "mood": mood,
    }
    OUT.parent.mkdir(exist_ok=True)
    bad = [k for k, v in feat.items() if isinstance(v, list) and len(v) not in (T, 12, STEPS)
           and k not in ("beats", "downbeats", "sections")]
    assert not bad, "逐帧通道长度不等于 nframes: %s" % [(k, len(feat[k])) for k in bad]
    OUT.write_text(json.dumps(feat, separators=(",", ":"), default=jsn))
    plot(feat, bn, rms, times, f0b, bass_voiced, pf, pattern, sections, Simg)
    print("[ok] %.1fs  frames %d  -> %s" % (dur, T, OUT.name))
    print("     tempo %.2f BPM ±%.2f (beat %.3fs, bar %.2fs)  lock %.4f = %.1fx 随机  置换检验 p=%.3f (零假设 p95=%.4f) %s"
          % (bpm, tres, period / FPS, period * 4 / FPS, lock, lock / chance, pval, null95,
             "显著" if pval < 0.05 else "不显著"))
    print("     定相比 %.2f  下拍位 %d %s" % (score, db_idx, db_weights))
    print("     低频竞争调制线 %.1f bpm (lock %.4f) —— 与宽带拍点不重合，节奏层是松耦合的"
          % (low_bpm, low_lock))
    print("     key %s %s r=%.2f  chroma top: %s" % (key["name"], key["mode"], key["corr"],
          ", ".join("%s %.3f" % (n, v) for n, v in sorted(zip(NOTE, key["profile"]), key=lambda z: -z[1])[:5])))
    print("     energy share: %s" % json.dumps(shares))
    print("     hi(>=%.0fHz 带均值) 逐 20s: %s" % (HI_CUT_HZ, " ".join("%.2f" % hi_band[i:i + int(20 * FPS)].mean() for i in range(0, T, int(20 * FPS)))))
    print("     mood: bright %.2f dyn %.2f centroid %.0fHz flat %.4f offgrid %.2f regularity %.2f tension %.2f"
          % (mood["brightness_mean"], mood["dynamic_range"], mood["centroid_mean_hz"],
             mood["flatness_mean"], offgrid, mood["bar_regularity"], mood["tension_mean"]))
    print("     bass line: %d notes (%.2f/s) range %s mean %.1f step %.2f st | voice: %d notes"
          % (len(bass_notes), mood["bass_voiced_share"], feat["melody"]["bass_range_midi"],
             feat["melody"]["bass_mean_midi"], feat["melody"]["bass_step_mean_semitone"], len(voice_notes)))
    for k in ("kick", "punch", "grit"):
        v = pattern[k]
        print("   %-5s 事件 %4d 次  跨小节一致性 %.2f |%s|" % (k, nev[k], cons[k], "".join(
            "█▓▒░"[min(3, int(x * 3.99))] if x > 0.02 else "·" for x in v)))
    print("   sections (%d):" % len(sections))
    for s in sections:
        print("   %6.1f-%6.1fs %-8s rms %.2f bright %+.2f noise %.3f cent %.0f dens %.2f tens %.2f bass %.0f pc %s ost %.1fb"
              % (s["start"], s["end"], s["role"], s["rms"], s["bright"], s["noise"],
                 s["cent"], s["onset_density"], s["tension"], s["bass_midi"], s["pc"], s["ostinato_beats"]))
    return 0


def plot(feat, bn, rms, times, f0b, bass_voiced, pf, pattern, sections, Simg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(5, 1, figsize=(16, 15), gridspec_kw={"height_ratios": [3, 2, 2, 1, 2]})
    t = times
    ax[0].pcolormesh(t, feat["meta"]["band_edges_hz"][:-1], bn, cmap="magma", shading="auto")
    ax[0].set_yscale("log")
    ax[0].set_ylabel("band Hz")
    ax[0].set_title("48 log-band spectrum + section boundaries (cyan)")
    ax[1].plot(t, rms / (rms.max() + 1e-9), lw=.7, color="black", label="rms")
    ax[1].plot(t, np.asarray(feat["lowhigh"]) / 255, lw=.7, color="tab:orange", label="bright")
    ax[1].plot(t, np.asarray(feat["tension"]) / 255, lw=.7, color="tab:purple", label="harmonic tension")
    for b in feat["beats"]:
        ax[1].axvline(b, color="crimson", lw=.3, alpha=.45)
    for b in feat["downbeats"]:
        ax[1].axvline(b, color="blue", lw=.8, alpha=.5)
    ax[1].legend(fontsize=7)
    ax[1].set_ylabel("norm")
    ax[1].set_title("rms / brightness / tension, beat grid (red) and bars (blue)")
    for k, c in (("kick", "tab:blue"), ("punch", "tab:red"), ("grit", "tab:green")):
        ax[2].plot(t, norm_i(pf[k])[:len(t)], lw=.7, label=k, color=c)
    ax[2].plot(t, np.where(bass_voiced, f0b / 300.0, np.nan), lw=1.3, color="black", alpha=.8, label="bass f0/300")
    ax[2].legend(fontsize=7)
    ax[2].set_ylabel("percussion + bass contour")
    M = np.array([pattern["kick"], pattern["punch"], pattern["grit"]]) * 3
    ax[3].imshow(M, aspect="auto", cmap="magma", vmin=0, vmax=3)
    ax[3].set_yticks(range(3))
    ax[3].set_yticklabels(["kick", "punch", "grit"], fontsize=8)
    ax[3].set_xticks(range(16))
    ax[3].set_title("16th-note drum pattern")
    ax[4].imshow(Simg, cmap="viridis", extent=[0, feat["meta"]["duration"], feat["meta"]["duration"], 0], aspect="auto")
    ax[4].set_ylabel("self-similarity")
    ax[4].set_xlabel("s")
    for a2 in (ax[0], ax[1], ax[2]):
        a2.set_xlim(0, feat["meta"]["duration"])
    for s in sections:
        ax[0].axvline(s["start"], color="cyan", lw=.6, alpha=.6)
    fig.tight_layout()
    fig.savefig(str(PLOT), dpi=95)
    plt.close(fig)
    print("[ok] plot -> %s" % PLOT.name)


def selftest() -> int:
    """对照实验：合成一个已知 BPM 的节拍器，验证估计器能把它认出来。

    没有这一步，"本曲锁定度只有 3 倍随机"这句话无法区分"曲子确实松散"和"我算错了"。
    """
    sr, fps, bpm_true = 22050, 30.0, 120.0
    y = np.zeros(int(40 * sr))
    for b in range(int(40 * sr * bpm_true / 60)):
        n = int(b * sr * 60.0 / bpm_true)
        L = int(0.09 * sr)
        if n + L >= len(y):
            break
        y[n:n + L] += np.exp(-np.arange(L) / (0.013 * sr)) * np.sin(2 * np.pi * 55 * np.arange(L) / sr)
        if b % 2 == 1:
            y[n:n + int(0.02 * sr)] += np.random.RandomState(b).randn(int(0.02 * sr)) * 0.06
    o = librosa.onset.onset_strength(y=y, sr=sr, hop_length=int(sr / fps))
    locks, chance = tempo_lock(o, fps, 95.0, 150.0)
    lk, bp_c = max(locks, key=lambda z: z[0])
    bp, tres = refine_tempo(o, fps, bp_c)
    err = abs(bp - bpm_true)
    sc, ph = fit_phase(o, fps * 60.0 / bp, len(o), fps)
    print("[selftest] 合成节拍器真值 %.1f BPM -> 粗峰 %.2f, 重心细化 %.2f (err %.2f, 分辨率 ±%.2f BPM) lock %.3f = %.1fx 随机, 定相比 %.2f"
          % (bpm_true, bp_c, bp, err, tres, lk, lk / chance, sc))
    assert err <= tres + 0.3, "估计器未能在对照信号上还原已知 BPM（误差超出 FFT 分辨率）"
    assert lk / chance > 8, "对照信号锁定倍数过低，估计器失效"
    # 反例 1：白噪声不应出现显著锁定
    n2 = np.random.RandomState(0).randn(int(40 * sr))
    o2 = librosa.onset.onset_strength(y=n2, sr=sr, hop_length=int(sr / fps))
    om2, nu2, p2, _ = lock_perm_pvalue(o2, fps)
    print("[selftest] 白噪声对照 -> 最大 lock %.4f (零假设 p95 %.4f), 置换检验 p=%.3f (应不显著)"
          % (om2, nu2, p2))
    assert p2 > 0.05, "白噪声上出现假显著锁定，指标不可信"
    # 反例 2：只有缓慢起伏、无节拍的信号也不应显著
    slow = 0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * np.arange(int(40 * fps)) / fps)
    o3 = norm_i(slow)
    om3, nu3, p3, _ = lock_perm_pvalue(o3, fps)
    print("[selftest] 0.05Hz 慢调制对照 -> lock %.4f, p=%.3f (应不显著)" % (om3, p3))
    assert p3 > 0.05, "慢调制被误判成节拍"
    # 正例的显著性
    omx, nux, px, _ = lock_perm_pvalue(o, fps, 95.0, 150.0)
    print("[selftest] 合成节拍器置换检验 p=%.4f (应显著)" % px)
    assert px < 0.05, "真节拍信号未通过显著性检验"
    print("[selftest] PASS：估计器在真值上还原并判显著，在噪声/慢调制上不误报。")
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest() if "--selftest" in sys.argv else main())
