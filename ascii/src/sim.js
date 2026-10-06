// v3：每帧纯函数于 f。语法＝单色青绿磷光辉 + 相干处才上色 + 余辉拖影 + 3D 旋转核心。
// 全片底色 teal(亮度阶)；色相只在时钟域相干处（CLKD 色标尺、导管交汇）按权重浮现，危机泛红。
// 运动体（3D 核心 / flit / 能量脉冲）在 f、f-Δ、f-2Δ 解析采样、递减亮度叠加 → 拖尾（仍可 seek）。
import { buildLayout } from "./layout.js";
import { clamp, hash32, rnd, rnd1, teal, tint, rot, project, torus, makeCam } from "./util.js";

const DENS = " .:-=+*oO#%&@".split("");
const DG = (i) => DENS[Math.max(0, Math.min(DENS.length - 1, i | 0))];
const NOISE = "#%&@$?!/\\|(){}[]=+*~".split("");
const FLIT = "><^v".split("");
const RED = [255, 96, 84], PALE = [206, 222, 218];

export const DOMS = [
  { key: "CLKD", label: "时钟分发", ch: "rms",   bpm: 119.26, gain: 0.10, band: [0, 47],  color: [120, 220, 210] },
  { key: "FE",   label: "前端流水线", ch: "pulse", bpm: 122.0,  gain: 0.22, band: [12, 26], color: [70, 205, 235] },
  { key: "EX",   label: "标量执行",   ch: "kick",  bpm: 105.0,  gain: 0.30, band: [2, 14],  color: [245, 175, 70] },
  { key: "MAT",  label: "矩阵运算",   ch: "bass",  bpm: 142.0,  gain: 0.34, band: [0, 12],  color: [160, 120, 255] },
  { key: "MEM",  label: "存储层次",   ch: "hi",    bpm: 133.0,  gain: 0.18, band: [30, 47], color: [95, 235, 155] },
  { key: "REG",  label: "寄存器·退休", ch: "voice", bpm: 96.0,   gain: 0.26, band: [20, 36], color: [240, 120, 205] },
];
const ACT = { boot:{b:.2}, spread:{b:.5}, chorus:{b:.72}, shift:{b:.45}, load:{b:.85},
  peak:{b:.95,g:.55}, glitch:{b:.9,g:1}, drain:{b:.55,g:.28}, hold:{b:.4}, blackout:{b:.1}, silence:{b:0} };
const MOOD = { boot:"苏醒", spread:"加速", chorus:"繁忙", shift:"转冷", load:"满载", peak:"临界", glitch:"危机", drain:"退潮", hold:"残响", blackout:"衰竭", silence:"寂灭" };

export function createSim(pack) {
  const L = buildLayout(pack);
  const { COLS, ROWS, cellKind } = L;
  const N = COLS * ROWS, T = pack.T, fps = pack.fps, NB = pack.NB;
  const gCh = new Uint8Array(N), gR = new Uint8Array(N), gG = new Uint8Array(N), gB = new Uint8Array(N), gA = new Uint8Array(N);
  const chOf = (n) => pack.ch[n] || new Uint8Array(T);
  const band = (b, f) => pack.band(clamp(b, 0, NB - 1), f);
  const TOR = torus(1.5, 0.62, 14, 7);

  const cum = {}, peak = {};
  DOMS.forEach((d) => { const a = chOf(d.ch); const c = new Float32Array(a.length); let s = 0, mx = 0;
    for (let i = 0; i < a.length; i++) { s += a[i] / 255; c[i] = s; if (a[i] > mx) mx = a[i]; } cum[d.key] = c; peak[d.key] = Math.max(1, mx) / 255; });
  { const c = chOf("flat"); let mn = 255, mx = 0; for (let i = 0; i < c.length; i += 23) { if (c[i] < mn) mn = c[i]; if (c[i] > mx) mx = c[i]; } cum._fmin = mn / 255; cum._fmax = Math.max(mn / 255 + 1e-3, mx / 255); }

  const edges = L.dataflow.map(([a, b]) => { const A = L.byId.get(a), B = L.byId.get(b); if (!A || !B) return null;
    const cells = []; const steps = Math.max(2, Math.abs(B.cx - A.cx) + Math.abs(B.cy - A.cy));
    for (let s = 0; s <= steps; s++) { const fr = s / steps; cells.push(clamp(Math.round(A.cy + (B.cy - A.cy) * fr), 0, ROWS - 1) * COLS + clamp(Math.round(A.cx + (B.cx - A.cx) * fr), 0, COLS - 1)); }
    return { cells, a: A.dom, b: B.dom }; }).filter(Boolean);

  function domState(d, f) { const a = chOf(d.ch); const e = a[f] / 255;
    const ph = (d.bpm / 60) / fps * f + cum[d.key][f] * d.gain + rnd(f, 3, d.bpm | 0) * 0.001 * f;
    const fr = ph - Math.floor(ph);
    return { env: clamp(0.14 + 0.86 * Math.pow(1 - fr, 1.8) * (0.35 + 0.65 * (e / peak[d.key])), 0, 1), ph, e: clamp(e / peak[d.key], 0, 1) }; }

  let S = {}, mood = 1, entropy = 0, power = 1, role = "boot", fcur = 0, clip = null;

  // 最大合成：更亮者胜（拖尾/线条叠加不互相抹掉）
  function blend(p, code, r, g, b, a) { if (p < 0 || p >= N || a <= gA[p]) return; if (clip) { const y = (p / COLS) | 0; if (y < clip[0] || y > clip[1]) return; } gCh[p] = code; gR[p] = r; gG[p] = g; gB[p] = b; gA[p] = a; }
  function put(p, code, r, g, b, a) { if (p < 0 || p >= N) return; gCh[p] = code; gR[p] = r; gG[p] = g; gB[p] = b; gA[p] = a; }
  function text(cx, row, str, rgb, a) { row = clamp(row, 0, ROWS - 1); for (let i = 0; i < str.length; i++) { const x = clamp(cx + i, 0, COLS - 1); if (str[i] !== " ") blend(row * COLS + x, str.charCodeAt(i), rgb[0], rgb[1], rgb[2], a); } }
  function line(x0, y0, x1, y1, code, rgb, a) { const steps = Math.max(1, Math.round(Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0)) * 1.4));
    for (let i = 0; i <= steps; i++) { const u = i / steps; blend(Math.round(y0 + (y1 - y0) * u) * COLS + Math.round(x0 + (x1 - x0) * u), code.charCodeAt(0), rgb[0], rgb[1], rgb[2], a * (0.7 + 0.3 * (1 - Math.abs(0.5 - u) * 2))); } }

  function stateAt(f) {
    fcur = clamp(f | 0, 0, T - 1); const t = fcur / fps;
    role = pack.actAtFrame(fcur).role; const A = ACT[role] || ACT.spread;
    power = clamp(pack.electricF(fcur), 0, 1);
    const flat = chOf("flat")[fcur] / 255;
    const ent = clamp((flat - cum._fmin) / (cum._fmax - cum._fmin), 0, 1);
    entropy = clamp(((A.g || 0) + (ent > 0.72 ? (ent - 0.72) * 1.6 : 0) + (role === "glitch" ? .35 : 0)) * power, 0, 1);
    const env2 = Math.pow(1 - (t * pack.bpm2 / 60 - Math.floor(t * pack.bpm2 / 60)), 3), bass_on = chOf("bass_on")[fcur] / 255;
    mood = clamp(0.44 + 0.5 * A.b + 0.22 * (chOf("rms")[fcur] / 255) + 0.18 * bass_on * env2, 0, 1) * (0.35 + 0.65 * power);
    DOMS.forEach((d) => S[d.key] = domState(d, fcur));

    gCh.fill(32); gR.fill(0); gG.fill(0); gB.fill(0); gA.fill(0);
    const shot = shotFor(t, role);
    if (shot.mode === "focus" && shot.target === "MAT") sceneMat();
    else {
      for (const blk of L.blocks) {
        chrome(blk);
        if (blk.id === "MAT") core3D(blk);
        else if (blk.id === "CLKD") clockRuler(blk);
        else if (blk.id === "PSU") psu(blk);
        else if (blk.id === "INT") interrupt(blk);
        else spectro(blk, blk.dom || "FE");
      }
      conduits();
      if (entropy > 0.3) crisis();
    }
    applyPower();
    return { t, role, power, ent, glitch: entropy, mood, S, shot };
  }

  function shotFor(t, role) {
    if (role === "load" || role === "peak") return { mode: "focus", target: "MAT" };
    return { mode: "wide" };
  }

  const hex2 = (v) => ((v & 255).toString(16).toUpperCase().padStart(2, "0"));
  const rep = (ch, n) => ch.repeat(Math.max(0, n | 0));
  // 三维英雄场景：systolic 分层爆炸图（输入平面在下 → MAC 高度场 → 输出平面在上，逐层炸开）
  function sceneMat() {
    const { Q, qn } = L; const M = qn[0], K = qn[1]; const n = Math.min(M, 8);
    const k = Math.floor(S.MAT.ph % K), t = fcur / fps;
    const act = pack.actAtFrame(fcur); const unfold = clamp((t - act.start) / 1.6, 0, 1);
    const cam = makeCam(0.98, t * 0.30, 9.5, COLS * 0.5, ROWS * 0.5, COLS * 1.7);
    const sep = 2.2 * unfold, half = (n - 1) / 2, gx = 0.5, hmax = 3.4;
    const H = (i, j) => { let a = 0; for (let kk = 0; kk <= k && kk < qn[1]; kk++) a += Q[i][kk] * Q[j][kk]; return a; };
    const fog = (z) => clamp((13.5 - z) / 7, 0.3, 1);
    const prims = [];
    const seg = (a, b, code, rgb, al) => { const st = Math.max(1, Math.round(Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1])) * 1.3)); for (let s = 0; s <= st; s++) { const u = s / st; blend(Math.round(a[1] + (b[1] - a[1]) * u) * COLS + Math.round(a[0] + (b[0] - a[0]) * u), code.charCodeAt(0), rgb[0], rgb[1], rgb[2], al * fog((a[2] + b[2]) / 2)); } };
    // 地面网格（lattice 足迹）
    const bx = half * gx + 0.4, bz = half * gx + 0.4;
    for (let i = 0; i < n; i++) { const a = cam.project((i - half) * gx, 0, -bz), b = cam.project((i - half) * gx, 0, bz); prims.push({ z: (a[2] + b[2]) / 2, run: () => seg(a, b, '.', teal(0.2), 70) }); }
    for (let j = 0; j < n; j++) { const a = cam.project(-bx, 0, (j - half) * gx), b = cam.project(bx, 0, (j - half) * gx); prims.push({ z: (a[2] + b[2]) / 2, run: () => seg(a, b, '.', teal(0.2), 70) }); }
    // 输入列 A[:,k]（下方平面）+ 连到柱阵前排
    const iy = -sep, iz = bz + 0.5;
    for (let i = 0; i < n; i++) { const v = Q[i][k], e = (v & 255) / 255; const pos = cam.project((i - half) * gx, iy, iz);
      prims.push({ z: pos[2], run: () => text(Math.round(pos[0]) - 1, Math.round(pos[1]), hex2(v), teal(0.7 + e * 0.3), 255) });
      const to = cam.project((i - half) * gx, 0, bz); prims.push({ z: (pos[2] + to[2]) / 2, run: () => seg(pos, to, '.', teal(0.4), 120) }); }
    // 输出行和（上方平面）
    const oy = sep, oz = -bz - 0.5;
    for (let i = 0; i < n; i++) { let s = 0; for (let j = 0; j < n; j++) s += H(i, j); const v = s & 255; const pos = cam.project((i - half) * gx, oy, oz);
      prims.push({ z: pos[2], run: () => text(Math.round(pos[0]) - 1, Math.round(pos[1]), hex2(v), teal(0.7 + (v / 255) * 0.3), 255) });
      const fr = cam.project((i - half) * gx, 0, -bz); prims.push({ z: (pos[2] + fr[2]) / 2, run: () => seg(fr, pos, '.', teal(0.4), 120) }); }
    // 中央 3D 柱阵：64 累加器各自升起（远→近 painter 遮挡）
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) { const raw = H(i, j); const e = (raw & 255) / 255; const h = clamp(raw / 180000, 0, 1);
      const base = cam.project((i - half) * gx, 0, (j - half) * gx), top = cam.project((i - half) * gx, h * hmax, (j - half) * gx); const z = base[2];
      const corrupt = entropy > 0.4 && rnd1(i, j, fcur) < entropy * 0.5;
      prims.push({ z, run: () => { const col = corrupt ? RED : teal(0.4 + e * 0.5); const al = fog(z); seg(base, top, corrupt ? '#' : '|', col, (corrupt ? 250 : 180) * al); blend(Math.round(top[1]) * COLS + Math.round(top[0]), corrupt ? 35 : (e > 0.5 ? 64 : 43), col[0], col[1], col[2], 255 * al); } }); }
    clip = [4, ROWS - 15]; prims.sort((a, b) => b.z - a.z); for (const p of prims) p.run(); clip = null;
    // ===== 标注层（屏幕空间，亮）=====
    text(2, 0, "MATRIX UNIT / SYSTOLIC ARRAY   [ 3D EXPLODED VIEW ]", PALE, 255);
    text(COLS - 24, 0, "C = A * B^T", PALE, 255);
    text(COLS - 34, 1, "A 8x10   B 8x10   C 8x8", teal(0.7), 240);
    text(2, 3, "INPUT A  >  operand column being fed in", teal(0.9), 255);
    text(2, Math.round(ROWS * 0.40), "MAC ARRAY  >  64 accumulator bars rise as k grows", teal(0.9), 255);
    text(2, ROWS - 13, "OUTPUT C  >  result drains when k=10", teal(0.9), 255);
    text(2, ROWS - 10, "STEP  k=" + k + "/" + K + " :  multiply A[:,k] by B[k,:], ADD into every cell", teal(0.95), 255);
    text(2, ROWS - 9, "C[i][j] = SUM_k  A[i,k] * B[k,j]      (partial sum grows each beat)", teal(0.75), 245);
    const ok = entropy < 0.4; let chk = 0; for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) chk = (chk + H(i, j)) & 255;
    text(2, ROWS - 7, "CHECKSUM 0x" + hex2(chk) + (ok ? "   OK  converging" : "   FAULT  metastable corruption"), ok ? teal(0.9) : RED, 255);
    text(2, ROWS - 5, "LEGEND   | bar = accumulator    @ hot top    # CORRUPT = fault    . grid / bus", teal(0.6), 235);
  }

  function chrome(blk) {
    const env = blk.dom && S[blk.dom] ? S[blk.dom].env : 0.4;
    for (let y = blk.r0; y <= blk.r1; y++) for (let x = blk.c0; x <= blk.c1; x++) {
      if (!(x === blk.c0 || x === blk.c1 || y === blk.r0 || y === blk.r1)) continue;
      const c = teal(0.18 + env * 0.18); put(y * COLS + x, (x === blk.c0 || x === blk.c1) ? 124 : 45, c[0], c[1], c[2], clamp(45 + env * 55, 0, 150) * power);
    }
    text(blk.c0 + 2, blk.r0 + 1, blk.id, PALE, 210 * power);
  }

  function spectro(blk, domKey) {
    const d = DOMS.find((x) => x.key === domKey) || DOMS[1]; const env = S[domKey] ? S[domKey].env : 0.5;
    const [bLo, bHi] = d.band; const rows = Math.max(1, blk.iy1 - blk.iy0 + 1), cols = Math.max(1, blk.ix1 - blk.ix0 + 1);
    for (let j = 0; j < cols; j++) { const fr = clamp(fcur - (cols - 1 - j), 0, T - 1);
      for (let rr = 0; rr < rows; rr++) { const bi = Math.round(bHi - (bHi - bLo) * (rr / Math.max(1, rows - 1)));
        let e = band(bi, fr) * (0.5 + 0.5 * env) * mood;
        if (entropy > 0.4 && rnd1(j, rr, fcur) < entropy * 0.3) e = 1 - e;
        const p = (blk.iy0 + rr) * COLS + (blk.ix0 + j);
        if (e < 0.12) { put(p, 46, ...teal(0.12), 20 * power); continue; }
        const c = teal(e); put(p, DG(Math.floor(e * DENS.length)).charCodeAt(0), c[0], c[1], c[2], clamp(55 + e * 200, 0, 250) * power);
      } }
  }

  // 3D 旋转核心（拖尾：tt, tt-Δ, tt-2Δ）
  function core3D(blk) {
    const cx = (blk.ix0 + blk.ix1) / 2, cy = (blk.iy0 + blk.iy1) / 2;
    const scale = Math.min((blk.ix1 - blk.ix0) / 6.6, (blk.iy1 - blk.iy0) / 3.6);
    const t = fcur / fps, { V, E } = TOR;
    for (let k = 2; k >= 0; k--) { const tt = t - k * 0.07, am = [1, 0.42, 0.16][k];
      const P = V.map((v) => { const [x, y, z] = rot(v[0], v[1], v[2], tt); return project(x, y, z, cx, cy, scale); });
      for (const [a, b] of E) { const [x, y, z] = P[a], [xx, yy, zz] = P[b]; const near = (z + zz) < 0;
        const e = clamp(0.25 + (1.6 + (z + zz) / 2) * 0.28, 0.05, 1) * mood * am;
        const col = entropy > 0.4 && rnd1(a, b, fcur) < entropy * 0.4 ? RED : teal(0.35 + e * 0.5);
        line(x, y, xx, yy, near ? "." : ":", col, clamp(e * 220, 0, 250) * power);
      }
      if (k === 0) for (let i = 0; i < V.length; i += 2) { const [x, y, z] = P[i]; const e = clamp(0.5 + z * 0.2, 0.1, 1) * mood; blend(Math.round(y) * COLS + Math.round(x), z > 0 ? 64 : 43, ...teal(0.55 + e * 0.4), clamp(e * 230, 0, 250) * power); }
    }
  }

  function clockRuler(blk) {
    const cols = blk.ix1 - blk.ix0 + 1;
    for (let j = 0; j < cols; j++) {
      let r = 0, g = 0, b = 0, tot = 0, active = 0;
      DOMS.forEach((d) => { const fr = (S[d.key].ph + j * 0.05) % 1; const e = Math.pow(1 - fr, 2.4) * mood;
        if (e > 0.4) active++; r += d.color[0] * e; g += d.color[1] * e; b += d.color[2] * e; tot += e; });
      const base = teal(clamp(tot * 0.4, 0, 1));
      const w = clamp((active - 1) / (DOMS.length - 1), 0, 1);                 // 相干度：多域同时亮才上色
      const col = tint(base, [r / Math.max(1, tot), g / Math.max(1, tot), b / Math.max(1, tot)], w);
      const idx = clamp(Math.floor(tot * DENS.length * 0.6), 0, DENS.length - 1);
      blend((blk.iy0) * COLS + (blk.ix0 + j), DG(idx).charCodeAt(0), col[0], col[1], col[2], clamp(40 + tot * 120, 0, 240) * power);
    }
  }

  function psu(blk) {
    for (let y = blk.iy0; y <= blk.iy1; y++) for (let x = blk.ix0; x <= blk.ix1; x++) {
      const rad = rnd1(x, y, 31); const e = (0.5 + 0.5 * Math.sin((y - blk.iy0) * 0.7 - S.CLKD.ph * 5)) * mood;
      if (rad < e * 0.7) { const c = teal(0.4 + e * 0.5); blend(y * COLS + x, DG(4 + ((e * 10) | 0)).charCodeAt(0), c[0], c[1], c[2], clamp(60 + e * 190, 0, 250) * power); }
    }
    for (let s = 0; s < 3; s++) for (let k = 2; k >= 0; k--) { const ph = ((S.CLKD.ph * 0.5 - k * 0.02 + s / 3) % 1 + 1) % 1; const px = blk.c0 + Math.floor(ph * (blk.c1 - blk.c0)); blend(blk.r1 * COLS + clamp(px, 0, COLS - 1), 61, ...teal(0.7), clamp(240 * [1, 0.4, 0.16][k], 0, 250) * power); }
  }

  function interrupt(blk) { const onset = chOf("onset")[fcur] / 255;
    for (let y = blk.iy0; y <= blk.iy1; y++) for (let x = blk.ix0; x <= blk.ix1; x++) { const e = rnd1(x, y, 5) * (0.3 + 0.7 * mood); if (e > 0.72) { const c = teal(0.3 + e * 0.4); blend(y * COLS + x, DG((e * DENS.length) | 0).charCodeAt(0), c[0], c[1], c[2], clamp(e * 150, 0, 200) * power); } }
    if (onset > 0.55) blend((blk.iy0 + (fcur % Math.max(1, blk.iy1 - blk.iy0))) * COLS + clamp(blk.cx, 0, COLS - 1), 33, ...RED, 245 * power); }

  function conduits() {
    for (const { cells, a, b } of edges) {
      for (const p of cells) { if (cellKind[p] === 3) continue; const c = teal(0.16); blend(p, 45, c[0], c[1], c[2], clamp(28 + 0.4 * mood * 50, 0, 80) * power); }
      const ea = S[a] ? S[a].env : 0.4, eb = S[b] ? S[b].env : 0.4, coh = clamp(Math.min(ea, eb) * 2, 0, 1); // 两端都亮=相干
      const da = DOMS.find((x) => x.key === a), db = DOMS.find((x) => x.key === b);
      const hue = da && db ? [(da.color[0] + db.color[0]) / 2, (da.color[1] + db.color[1]) / 2, (da.color[2] + db.color[2]) / 2] : teal(0.7);
      for (let s = 0; s < 2; s++) for (let k = 2; k >= 0; k--) {
        const ph = S[a] || S.FE; const pos = (((ph.ph - k * 0.03) * 0.3 + s * 0.5 + hash32(cells.length + s) / 4294967296) % 1 + 1) % 1 * (cells.length - 1);
        const ci = clamp(Math.floor(pos), 0, cells.length - 1); const base = teal(0.6); const col = tint(base, hue, coh);
        blend(cells[ci], k === 0 ? FLIT[(pos | 0) % 4].charCodeAt(0) : 46, col[0], col[1], col[2], clamp((255 - k * 80) * (0.4 + 0.6 * coh), 0, 255) * power);
      }
    }
  }

  function crisis() {
    if (fcur % 5 === 0) { const y = clamp(3 + (hash32(fcur) % (ROWS - 6)), 0, ROWS - 1); const sh = 2 + hash32(fcur + 1) % 4; const row = []; for (let x = 0; x < COLS; x++) row.push([gCh[y * COLS + x], gR[y * COLS + x], gG[y * COLS + x], gB[y * COLS + x], gA[y * COLS + x]]);
      for (let x = 0; x < COLS; x++) { const src = row[(x + sh) % COLS]; gCh[y * COLS + x] = src[0]; gR[y * COLS + x] = src[1]; gG[y * COLS + x] = src[2]; gB[y * COLS + x] = src[3]; gA[y * COLS + x] = src[4]; } }
    const sy = clamp((fcur * 3) % ROWS, 0, ROWS - 1); for (let x = 0; x < COLS; x++) { const p = sy * COLS + x; if (gA[p] > 50) { gR[p] = RED[0]; gG[p] = RED[1]; gB[p] = RED[2]; gA[p] = clamp(gA[p] + 40, 0, 255); } }
  }

  function applyPower() {
    if (power >= 0.98 && role !== "silence") return; const k = clamp(power, 0, 1);
    for (let p = 0; p < N; p++) { let a = gA[p] * (0.12 + 0.88 * k); if (role === "silence") a *= 0.08; if (a < 8) { gCh[p] = 32; a = 0; } gA[p] = a | 0; }
    if (role === "silence" && (fcur % 30) < 16) { const m = L.byId.get("MAT"); put(m.cy * COLS + clamp(m.cx, 0, COLS - 1), 95, ...PALE, 200); }
  }

  function snapshot() { let non = 0, bright = 0, red = 0, chroma = 0;
    for (let p = 0; p < N; p++) { const c = (gR[p] * 0.3 + gG[p] * 0.6 + gB[p]) * gA[p] / 255; if (gCh[p] !== 32) { non++; if (c > 120) bright++; if (gR[p] > 180 && gR[p] > gG[p] + 40) red++; const mx = Math.max(gR[p], gG[p], gB[p]), mn = Math.min(gR[p], gG[p], gB[p]); if (mx > 90 && mx - mn > 70) chroma++; } }
    return { non, bright, red, chroma }; }
  function renderLines(st) {
    return [
      `T=${st.t.toFixed(1)}s  ${MOOD[st.role] || st.role}  能量 ${(st.mood * 100) | 0}%  熵 ${(st.ent * 100) | 0}%  电源 ${(st.power * 100) | 0}%`,
      `时钟相位 ${DOMS.map((d) => `${d.key}${st.S[d.key].ph.toFixed(0)}`).join(" ")}  ← 各域永不对齐`,
      st.glitch > 0.4 ? `!! 相干崩溃 · 频谱撕裂` : `青绿磷光辉 · 相干处上色`,
    ];
  }
  return { L, COLS, ROWS, N, gCh, gR, gG, gB, gA, cellKind, stateAt, snapshot, renderLines, DOMS, MOOD };
}
