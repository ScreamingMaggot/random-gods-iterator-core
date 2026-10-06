// ASCII 渲染"乱序 CPU"镜头：上半屏=功能化组件（对齐一行）+ 总线；下半屏=大号"计算之心"3D 环面。
// 每个音触发一次 Grey Cloud 式放电（沿格走的锯齿特效线），经 IO 口连接心与各组件，取代简单线流。
// 统一语法：地址=黄 数据=青 控制=红 中断=紫 时钟=白。
import { clamp, makeCam, torus } from "./util.js";

const C = { addr: [245, 217, 10], data: [55, 230, 255], ctrl: [255, 90, 74], irq: [200, 107, 255], clk: [236, 255, 248],
  base: [46, 150, 140], text: [206, 232, 226], dim: [26, 74, 70], hit: [80, 230, 150], miss: [255, 92, 80] };
const FC = { addr: C.addr, data: C.data, ctrl: C.ctrl, irq: C.irq };
const FONT = "'DejaVu Sans Mono','Consolas','Courier New',monospace";
// 5×5 块字（艺术大字用），逐位 '1' 实心
const GLYPH = {
  T: ["11111", "00100", "00100", "00100", "00100"], R: ["11110", "11011", "11110", "11101", "11011"],
  I: ["11111", "00100", "00100", "00100", "11111"], P: ["11110", "11011", "11110", "11000", "11000"],
  L: ["11000", "11000", "11000", "11000", "11111"], E: ["11111", "11000", "11110", "11000", "11111"],
  A: ["01110", "11011", "11111", "11011", "11011"], F: ["11111", "11000", "11110", "11000", "11000"],
  M: ["10001", "11011", "10101", "10001", "10001"], O: ["01110", "11011", "11011", "11011", "01110"],
  N: ["11001", "11101", "11111", "10111", "10011"], " ": ["00000", "00000", "00000", "00000", "00000"],
};

// 1D 值噪声 + fbm（借 The Sun Station：日珥/日冕的 streamer 用它生成）
function h1(n) { n = (n ^ 61) ^ (n >>> 9); n = (n + (n * 3)) | 0; n ^= n >>> 4; n = (n * 0x27d4eb2d) | 0; n ^= n >>> 15; return (n >>> 0) / 4294967295; }
function vn(x) { const i = Math.floor(x), f = x - i, a = h1(i), b = h1(i + 1); return a + (b - a) * (f * f * (3 - 2 * f)); }
function fbm1(x) { return 0.6 * vn(x) + 0.3 * vn(x * 2.3 + 11) + 0.1 * vn(x * 4.9 + 37); }
const TOR = torus(1.8, 0.92, 22, 10);

// 组件：中心/尺寸 + 底/顶 IO 口
const STAGES = ["FETCH", "DECODE", "EXEC", "MEM", "WB"];
const NP = { FETCH: [12, 5], DECODE: [37, 5], EXEC: [62, 5], MEM: [87, 5], WB: [112, 5], BUS: [62, 10] };
const BLK = { IRQ: { x: 16, y: 20, w: 26, h: 10, col: "irq", bc: [255, 90, 190] }, REG: { x: 52, y: 20, w: 30, h: 10, col: "data", bc: [70, 220, 245] }, CACHE: { x: 86, y: 20, w: 22, h: 10, col: "addr", bc: [255, 200, 80] }, DRAM: { x: 112, y: 20, w: 18, h: 10, col: "data", bc: [95, 235, 150] } };
const HEART = { x: 64, y: 34 };

export function createCpuAscii(cpu, pack, COLS = 128, ROWS = 58) {
  const N = COLS * ROWS;
  const gCh = new Uint8Array(N), gR = new Uint8Array(N), gG = new Uint8Array(N), gB = new Uint8Array(N), gA = new Uint8Array(N);
  const canvas = document.getElementById("stage"); const ctx = canvas.getContext("2d");
  const bgc = document.createElement("canvas"); const bgx = bgc.getContext("2d");   // 背景离屏层（做毛玻璃）
  let W = 0, H = 0, cw = 1, chh = 1, ox = 0, oy = 0;
  let flashRGB = null;   // 场景可设全屏叠加色（生物工程失败闪红）[r,g,b,0..1]
  let clipMinY = 0, clipMaxY = 1e9, introY = 1e9;   // ③入场逐行改写：set() 按行裁剪；introY=刷新前沿
  const glitchAct = (pack.raw.acts || []).find((a) => a.role === "glitch");
  const climaxEnd = glitchAct ? glitchAct.end : pack.duration;   // 进度条终点＝高潮(glitch 幕)结束
  const loadAct = (pack.raw.acts || []).find((a) => a.role === "load");
  const sceneStart = loadAct ? loadAct.start : 62;               // 第二部分起点：场景从这里才亮起
  const spreadAct = (pack.raw.acts || []).find((a) => a.role === "spread");
  const bootEnd = spreadAct ? spreadAct.end : 22;                // 苏醒场景覆盖 0–22s
  const shiftAct = (pack.raw.acts || []).find((a) => a.role === "shift");
  const bioEnd = shiftAct ? shiftAct.start : 39;                 // 生物工程(chorus)结束 → 进入自我怀疑喘息窗
  const blackoutAct = (pack.raw.acts || []).find((a) => a.role === "blackout");
  const powerEnd = blackoutAct ? blackoutAct.start : 192.3;      // POWER 被腐化/断电的时刻
  const ease = (u) => u * u * (3 - 2 * u);                       // 平滑快进快出（morph 位移用）
  const BOOT = { ring: [0, 3], power: [3, 6], cpu: [6, 10], mem: [10, 14], vector: [14, 17], boot: [17, 20] };
  const PHASE = [[0, "POWER-ON SELF TEST  ·  INIT"], [3, "POWER RAIL  +12V  STABILIZING"], [6, "CPU · BUS · PIC  ONLINE"], [10, "CACHE · MEMCTRL · DRAM  TRAINING"], [14, "RESET VECTOR 0xFFFF0 · BIOS ROM"], [17, "BOOT SECTOR → 0x7C00 · 0xAA55"], [20, "SYSTEM READY · TRIPLE-AFFIRM GATE OPEN"]];
  const seg = (tt, a, b) => clamp((tt - a) / (b - a), 0, 1);     // 0→1 进度
  const RAM = { x0: 6, x1: COLS - 6, y: ROWS - 11 };             // 底部 1MB 内存条

  const set = (col, row, code, rgb, a) => { col |= 0; row |= 0; if (col < 0 || col >= COLS || row < 0 || row >= ROWS) return; if (row < clipMinY || row >= clipMaxY) return; const p = row * COLS + col; if (a <= gA[p]) return; gCh[p] = code; gR[p] = rgb[0]; gG[p] = rgb[1]; gB[p] = rgb[2]; gA[p] = a; };
  const txt = (col, row, s, rgb, a) => { for (let i = 0; i < s.length; i++) if (s[i] !== " ") set(col + i, row, s.charCodeAt(i), rgb, a); };
  const bit = (t, i) => { let x = (t * 2654435761 ^ i * 40503) >>> 0; x = Math.imul(x ^ (x >>> 15), 2246822519); return ((x >>> 13) & 1023) / 1023; };
  function box(cx, cy, w, h, rgb, label, glow) {
    const x0 = cx - (w >> 1), y0 = cy - (h >> 1), x1 = x0 + w - 1, y1 = y0 + h - 1;
    for (let x = x0; x <= x1; x++) { set(x, y0, 45, rgb, glow); set(x, y1, 45, rgb, glow); }
    for (let y = y0; y <= y1; y++) { set(x0, y, 124, rgb, glow); set(x1, y, 124, rgb, glow); }
    set(x0, y0, 43, rgb, glow); set(x1, y0, 43, rgb, glow); set(x0, y1, 43, rgb, glow); set(x1, y1, 43, rgb, glow);
    if (label) txt(x0 + 2, y0, label, C.text, 235);
    return { x0, y0, x1, y1 };
  }
  function square(x, amp, duty) { const ph = x - Math.floor(x); return (ph < duty ? amp : -amp) / (2 * Math.PI); }
  function aline(x0, y0, x1, y1, code, rgb, a) { const n = Math.max(1, Math.round(Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0)) * 1.4)); for (let i = 0; i <= n; i++) { const u = i / n; set(Math.round(x0 + (x1 - x0) * u), Math.round(y0 + (y1 - y0) * u), code, rgb, a); } }
  // Grey Cloud 式放电：沿格走的锯齿特效线 + 分支
  function bolt(x0, y0, x1, y1, seed, rgb, a) {
    const steps = Math.max(4, Math.round(Math.hypot(x1 - x0, (y1 - y0) * 2))); let px = x0, py = y0;
    for (let i = 1; i <= steps; i++) { const u = i / steps;
      const tx = x0 + (x1 - x0) * u + (bit(seed, i) - 0.5) * 8 * (1 - Math.abs(u - 0.5) * 1.6);
      const ty = y0 + (y1 - y0) * u + (bit(seed, i + 99) - 0.5) * 3;
      const dx = tx - px, dy = ty - py; const ch = Math.abs(dx) > Math.abs(dy) ? 45 : (dy < 0 ? 47 : 92);
      set(tx, ty, ch, rgb, a * (0.6 + 0.4 * bit(seed, i + 7)));
      if (bit(seed, i + 31) < 0.14) { set(tx + 2, ty, 45, rgb, a * 0.6); set(tx + 3, ty, 46, rgb, a * 0.5); }
      px = tx; py = ty; }
    set(x1, y1, 64, rgb, 255);
  }

  // ① 苏醒 POWER-ON：系统级全景——圆形加载动画(在业力符号同位) + 模块批次上电 + 电流沿总线扩散 +
  //    POST 自检 + 底部 1MB 内存条(复位向量/BIOS/0x7C00/CS:IP/A0-A19)，地址·数据·控制线真实流动。
  function sceneBoot(st, m) {
    const RCX = HEART.x, RCY = HEART.y, RRx = Math.min(COLS * 0.17, 21), RRy = RRx * 0.66;   // 与业力符号同位同尺寸（画在背景毛玻璃层）
    const PODY = 7, BUSY = 15, MPY = 47, MAPX0 = 8, MAPX1 = 120;
    const ob = seg(ttLocal(st), 0, BOOT.boot[1]);              // 全局启动进度 0→1（0..20s）
    const done = ttLocal(st) >= BOOT.boot[1];                  // ≥20s：完成，进入就绪保持
    const tt = ttLocal(st);
    const gold = [255, 210, 105];

    // 标题 / 阶段 / 语法图例
    txt(2, 0, "RANDOM GODS · ITERATOR CORE — COLD BOOT / POWER-ON", C.text, 245);
    let ph = PHASE[0][1]; for (const p of PHASE) if (tt >= p[0]) ph = p[1];
    txt(2, 1, ph, done ? C.hit : C.data, 245);
    txt(2, 2, "addr", C.addr, 230); txt(8, 2, "data", C.data, 230); txt(14, 2, "ctrl", C.ctrl, 230); txt(20, 2, "clk", C.clk, 230); txt(26, 2, "pwr", gold, 230);
    txt(COLS - 18, 0, "T+" + tt.toFixed(1) + "s", C.dim, 200);

    // 电流沿总线扩散（上电 3→14s 从左向右充能，节拍脉冲调制亮度）
    const charge = clamp(seg(tt, BOOT.power[0], BOOT.mem[1]), 0, 1);
    const beat = tt >= 4.4 ? (0.7 + 0.3 * Math.sin(st.tick * 0.55)) : 1;   // 时钟起振后的全局节拍脉冲
    for (let x = MAPX0; x <= MAPX1; x++) { const u = (x - MAPX0) / (MAPX1 - MAPX0), on = u <= charge;
      set(x, BUSY, on ? 61 : 45, on ? gold : C.dim, on ? 210 * beat : 55); }
    if (charge > 0.01 && charge < 1) { const hx = MAPX0 + charge * (MAPX1 - MAPX0); for (let k = 0; k < 4; k++) set(Math.round(hx - k), BUSY, k === 0 ? 42 : 61, [255, 240, 150], 255 - k * 55); }
    txt(MAPX0, BUSY - 1, "PWR BUS  VCC", gold, 200);

    // 模块批次点亮：9 个 pod（0 电源/时钟/复位 · 1 CPU/总线/PIC · 2 Cache/内存控/DRAM）
    const PODS = [["PSU", 0, gold], ["CLK", 0, C.clk], ["RST", 0, C.hit], ["CPU", 1, C.data], ["BUS", 1, C.data], ["PIC", 1, C.irq], ["CACHE", 2, C.addr], ["MEMC", 2, C.data], ["DRAM", 2, C.hit]];
    const pxOf = (i) => 12 + Math.round(i * (104 / 8));
    PODS.forEach(([name, b, col], i) => {
      const bstart = [BOOT.power[0], BOOT.cpu[0], BOOT.mem[0]][b], onAt = bstart + (i % 3) * 0.5;
      const lit = tt >= onAt, ramp = clamp((tt - onAt) / 0.5, 0, 1), x = pxOf(i);
      box(x, PODY, 11, 3, lit ? col : C.dim, name, lit ? Math.round(120 + 130 * ramp) : 45);
      if (!lit) return;
      // 电流从 pod 底部沿竖线注入总线（彗头下行 + 拖尾）
      const yy = PODY + 2, span = BUSY - yy; const u = ((st.tick * 0.06 + i * 0.13) % 1);
      for (let k = 0; k < 5; k++) { const uu = u - k * 0.09; if (uu < 0 || uu > 1) continue; set(x, Math.round(yy + uu * span), k === 0 ? 124 : 124, col, Math.round(255 * (1 - k / 5) * ramp)); }
      // 总线充能后 → 汇入核心加载环
      if (charge >= (x - MAPX0) / (MAPX1 - MAPX0)) { const fe = u; set(x, Math.round(BUSY), 43, gold, 255); void fe; }
    });
    // 总线中心 → 加载环顶 的馈电线（bus 充能过半才通电，彗头注入核心；就绪后停止）
    if (charge >= 0.5 && !done) { const y0 = BUSY + 1, y1 = RCY - RRy, u = (st.tick * 0.08) % 1;
      for (let y = y0; y <= y1; y++) set(RCX, y, 124, C.data, 70);
      set(RCX, Math.round(y0 + u * (y1 - y0)), 43, [150, 250, 255], 255); }

    // 加载环本体（进度弧 + spinner + 完成绿环 + √）画在背景毛玻璃层，见 drawLoader；此处仅留前景读数
    if (!done) txt(RCX - 14, RCY - RRy - 2, "BOOTING " + Math.round(ob * 100) + "%", C.data, 220);

    // POST 自检逐行输出（左栏，避开总线行 y=15）
    const PY = 18;
    const POST = [["PSU +12V/+5V .. OK", 3.6], ["CLOCK 119.3MHz  OK", 4.6], ["RESET #L ASSERT", 5.4], ["CPU CORE DETECT", 6.4], ["BUS ARBITER . OK", 7.6], ["PIC IRQ15 ... OK", 9.0], ["CACHE 16W/4S  OK", 11.4], ["MEMCTRL ..... OK", 12.6], ["DRAM TRAIN .. OK", 14.0], ["IVT 0000:0000 BUILD", 14.8], ["VECTOR F000:FFF0", 15.8], ["BOOT 0x7C00 AA55", 18.8]];
    txt(4, PY, "POST SELF-TEST", C.text, 220);
    POST.forEach(([s, at], i) => { if (tt < at) return; const y = PY + 1 + i; const fresh = tt - at < 0.5, blink = fresh && (st.tick % 6 < 3);
      txt(4, y, s, /OK|BUILD|AA55/.test(s) ? C.hit : C.data, blink ? 90 : 225); });

    // 右栏：时钟波形 + CS:IP + A0-A19 地址线 +（保护模式 GDT/CR0.PE/A20）
    const rx = 90; txt(rx, PY, "CLK / ADDRESS / CONTROL", C.text, 210);
    for (let i = 0; i < 30; i++) { const hi = tt >= 4.4 ? square(i * 0.5 - st.tick * 0.18, 1, 0.5) > 0 : false; set(rx + i, PY + 2, hi ? 95 : 46, C.clk, hi ? 220 * beat : 45); }
    txt(rx, PY + 4, "CLK 119.3", C.dim, 180);
    const tgt = tt < 14 ? 0 : tt < 16 ? 0xFFFF0 : tt < 18 ? 0xF0000 : 0x7C00;
    const csip = tt < 18 ? "F000:FFF0" : "07C0:0000";
    txt(rx, PY + 5, "CS:IP " + csip, tgt ? C.data : C.dim, 240);
    txt(rx, PY + 6, "A0-A19 " + tgt.toString(16).toUpperCase().padStart(5, "0"), C.addr, 240);
    for (let b = 0; b < 20; b++) { const on = ((tgt >> b) & 1) === 1; set(rx + b, PY + 7, on ? 35 : 45, on ? C.addr : C.dim, on ? 235 : 55); }
    if (tt >= 17) { txt(rx, PY + 9, "GDT  LOADED", C.irq, 225); const pe = tt >= 19; txt(rx, PY + 10, "CR0.PE " + (pe ? "1 PROT" : "0 REAL"), pe ? C.hit : C.ctrl, 240);
      txt(rx, PY + 11, "A20 GATE " + (tt >= 18.4 ? "OPEN" : "CLOSED"), tt >= 18.4 ? C.hit : C.dim, 235); }

    // 底部 1MB 内存条：0x00000–0xFFFFF；BIOS ROM 高亮 / 复位向量 / IVT / 0x7C00 引导扇区飞入 / CS:IP 指针
    const posOf = (a) => Math.round(MAPX0 + (a / 0xFFFFF) * (MAPX1 - MAPX0));
    txt(MAPX0, MPY - 3, "1MB MEMORY MAP  0x00000 — 0xFFFFF", C.text, 220);
    for (let x = MAPX0; x <= MAPX1; x++) set(x, MPY, 45, C.dim, 90);
    // BIOS ROM 顶部 F0000–FFFFF（上电即高亮）
    if (tt >= 5) for (let x = posOf(0xF0000); x <= MAPX1; x++) set(x, MPY, 61, C.addr, 150 + 60 * Math.sin(st.tick * 0.3 + x));
    txt(posOf(0xF0000), MPY - 1, "BIOS ROM", C.addr, 230);
    // IVT 中断向量表（POST 后 0x000–0x400 建立）
    if (tt >= 14.8) { for (let x = MAPX0; x <= posOf(0x400); x++) set(x, MPY, 58, C.hit, 200); txt(MAPX0, MPY + 1, "IVT", C.hit, 220); }
    // 0x7C00 引导扇区飞入：18→19.5s 从左缘飞入，落位后显 AA55
    if (tt >= BOOT.boot[0]) { const p = seg(tt, BOOT.boot[0] + 0.3, BOOT.boot[1] - 0.5); const tx = posOf(0x7C00); const bx = Math.round(MAPX0 + p * (tx - MAPX0));
      for (let k = 0; k < 6; k++) if (bx - k >= MAPX0) set(bx - k, MPY - 2, "EB519048"[k].charCodeAt(0), C.data, 255 - k * 30);
      if (p >= 1) { set(tx, MPY, 61, C.hit, 255); set(tx + 1, MPY, 61, C.hit, 255); txt(tx + 2, MPY + 1, "0x7C00 AA55", C.hit, 245); } }
    // 复位向量 0xFFFF0 高亮（14–17s 闪烁，随后 CS:IP 指针移向 BIOS→0x7C00）
    if (tt >= 14 && tt < 17.5) { const x = posOf(0xFFFF0), bl = (st.tick % 8) < 5; set(x, MPY, 60, bl ? C.miss : C.addr, 255); if (bl) txt(x - 5, MPY + 1, "RST 0xFFFF0", C.miss, 245); }
    // CS:IP 指针（caret 沿内存条移动到当前取指地址）
    if (tt >= 14) { const cx = posOf(tgt); set(cx, MPY + 2, 94, C.clk, 255); set(cx, MPY + 3, tgt === 0x7C00 ? 48 : 46, C.clk, 180); }
    txt(MAPX1 - 4, MPY + 3, "0xFFFFF", C.dim, 170); txt(MAPX0, MPY + 3, "0x00000", C.dim, 170);

    // 地址/数据/控制三条总线：右缘自上而下真正流动（黄=地址 青=数据 红=控制）
    const laneCols = [C.addr, C.data, C.ctrl];
    const laneOn = [BOOT.cpu[0], BOOT.mem[0], BOOT.vector[0]];
    for (let li = 0; li < 3; li++) { const lx = Math.min(COLS - 1, MAPX1 + 1 + li * 2); const col = laneCols[li]; const active = tt >= laneOn[li];
      for (let y = BUSY; y <= MPY; y++) set(lx, y, 46, C.dim, active ? 55 : 25);
      if (!active) continue; const u = (st.tick * 0.05 + li * 0.2) % 1, yy = Math.round(BUSY + u * (MPY - BUSY));
      set(lx, yy, li === 2 ? 60 : 65 + ((st.tick * 3 + li) % 6), col, 255);   // 控制=箭头，地址/数据=hex
      for (let k = 1; k <= 4; k++) { const py = yy - k; if (py < BUSY) break; set(lx, py, ((st.tick * 5 + k * 3 + li * 7) % 10) + 48, col, Math.round(230 - k * 45)); } }
  }

  function ttLocal(st) { return st.tick / pack.fps; }

  // ② 生物工程 / 基因锁突破（22–62s）：LOGIC ANALYZER 下沉到底并共享；其中一条载波分离展开为
  //    横穿左 3/4 的 DNA 双螺旋进度条（随音频噪声抖动，绿=已扫描/灰=未解锁）；顶部降下生化反应设备
  //    向随机碱基位点注入；右侧 1/4 独立"标本舱"生成扭曲·复杂·崩坏的生体——全部失败，每次失败全屏闪红重试。
  const BASE = { A: [120, 230, 140], T: [255, 150, 90], G: [245, 217, 10], C: [55, 230, 255] };
  const COMP = { A: "T", T: "A", G: "C", C: "G" };
  const OPS = [["MODIFY", C.addr], ["REPLACE", C.data], ["SHIFT", C.irq], ["SPLICE", C.hit], ["METHYLATE", C.clk]];
  const mixc = (a, b, u) => [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];
  const baseAt = (x) => "ATGC"[(Math.imul(x + 7, 2654435761) >>> 30) & 3];
  function sceneBio(st, m) {
    const tt = ttLocal(st);
    const mo = 1, mr = 1;                                          // ②布局直接就位（缓慢移动已省去，改由 1s 字符阵变换进入）
    const HX0 = 2, HX1 = 96, HCy = 40, Htwist = 0.5, AMAX = 4.6;
    const DIVX = 99, CX0 = 101, CX1 = COLS - 2, CCX = (CX0 + CX1) >> 1;
    const amp = AMAX;
    const laneY0 = 52, laneX0 = 2, spread = 1;                     // 分析器/螺旋直接落位
    const BP = 60 / (pack.bpm || 119.26), A0 = 23, APER = BP * 2;   // 一轮 = 两拍，踩点
    const at = tt >= A0 ? Math.floor((tt - A0) / APER) : -1;
    const u = at >= 0 ? (tt - A0) / APER - at : 0;
    const ai = Math.max(0, at), seed = ai * 97 + 13;
    const nz = (x) => fbm1(x * 0.18 + st.tick * 0.04) - 0.5;
    const fail = at >= 0 && u >= 0.78;

    // 标题 / 阶段 / 图例
    txt(2, 0, "RANDOM GODS · ITERATOR CORE — GENOME FORGE / GENE-LOCK BREACH", C.text, 245);
    txt(2, 1, at < 0 ? "UNFOLDING CARRIER · CALIBRATING HELIX" : "ROUND #" + String(ai + 1).padStart(2, "0") + "  ·  3x PARALLEL EDIT  ->  INCUBATE -> ASSAY -> REJECT", C.data, 245);
    txt(2, 2, "A", BASE.A, 235); txt(4, 2, "T", BASE.T, 235); txt(6, 2, "G", BASE.G, 235); txt(8, 2, "C", BASE.C, 235);
    txt(11, 2, "genome", C.hit, 220); txt(19, 2, "edit", C.addr, 220); txt(25, 2, "reject", C.miss, 220);
    txt(COLS - 18, 0, "T+" + tt.toFixed(1) + "s", C.dim, 200);

    // 顶部：生化反应设备（端口朝下向螺旋片段施加操作）
    const PODY = 5;
    const PODS = [["SEQUENCER", 12], ["SPLICER", 34], ["INCUBATOR", 56], ["ASSAY", 78]];
    PODS.forEach(([nm, x]) => { box(x, PODY, 17, 3, C.base, nm, 150); set(x, PODY + 2, 124, C.data, 180); });
    // 本轮 3 个并发操作器：各锁一个片段、各做一种操作
    const ops = [];
    for (let j = 0; j < 3; j++) { const sj = seed + j * 131; ops.push({
      tx: Math.round(HX0 + 4 + bit(sj, 3) * (HX1 - HX0 - 8)), pod: PODS[(ai + j) % 4][1], o: OPS[(ai * 3 + j) % OPS.length], sj }); }
    if (at >= 0 && u < 0.78) for (const e of ops) { const y0 = PODY + 2, y1 = HCy - amp, p = clamp(u / 0.12, 0, 1);   // 探针光束射向目标片段
      aline(e.pod, y0, e.tx, y0 + (y1 - y0) * p, 46, e.o[1], 120);
      set(Math.round(e.pod + (e.tx - e.pod) * p), Math.round(y0 + (y1 - y0) * p), 62, e.o[1], 255); }

    // 中部：突变日志（本轮 3 个并发操作，全部 REJECT）
    if (at >= 0) { txt(2, 12, "MUTATION LOG  ·  TARGET / OP / RESULT", C.text, 200);
      ops.forEach((e, j) => { const pos = 0x1000 + ((bit(e.sj, 1) * 0xefff) | 0);
        txt(2, 13 + j, "POS 0x" + pos.toString(16).toUpperCase().padStart(4, "0") + "   " + e.o[0].padEnd(9) + "   " + (fail ? "REJECT" : "EDIT.."), e.o[1], 230); }); }

    // 隐约闪烁的红色基因锁警告框（所有操作都在触碰基因锁）
    if (tt >= 25.5) { const wa = (0.30 + 0.30 * Math.sin(st.tick * 0.22)) * (bit(st.tick, 5) < 0.9 ? 1 : 0.25);
      const bx0 = 1, bx1 = 97, by0 = 25, by1 = 49;
      for (let x = bx0; x <= bx1; x++) { set(x, by0, 45, C.miss, wa * 130); set(x, by1, 45, C.miss, wa * 130); }
      for (let y = by0; y <= by1; y++) { set(bx0, y, 124, C.miss, wa * 130); set(bx1, y, 124, C.miss, wa * 130); }
      txt(4, by0, "!! GENE-LOCK BREACH  //  LOCK INTEGRITY AT RISK  !!", C.miss, wa * 210);
      txt(4, by1, "!!  EVERY EDIT THREATENS THE LOCK  //  SPECIMEN MORTALITY 100%  !!", C.miss, wa * 190); }

    // DNA 双螺旋（活体基因组，非进度条）：3 条射线同时对随机片段 修改/替换/移位/拼接/修饰
    for (let x = HX0; x <= HX1; x++) {
      const th = (x - HX0) * Htwist + st.tick * 0.05, s = Math.sin(th), j = nz(x);
      const a = Math.max(0.6, amp * (0.85 + 0.5 * Math.abs(j)));
      const y1 = HCy + a * s + j * 1.4, y2 = HCy - a * s + j * 1.4;
      let tg = null; if (at >= 0 && u < 0.78) for (const e of ops) if (Math.abs(x - e.tx) <= 4) { tg = e; break; }
      const col = tg ? tg.o[1] : C.hit, br = tg ? 255 : 200;
      set(x, Math.round(y1), 46, col, br); set(x, Math.round(y2), 46, col, br);
      set(x, Math.round(y1) + (s > 0 ? 1 : -1), 46, col, br * 0.5);
      if (x % 3 === 0 && Math.abs(s) > 0.3) {                       // 横档 = 碱基对
        const scr = tg && u < 0.62 ? "ATGC"[((st.tick >> 1) + x) & 3] : baseAt(x);   // 编辑中被扰动的碱基
        const bcol = tg ? tg.o[1] : BASE[scr];
        const ylo = Math.round(Math.min(y1, y2)), yhi = Math.round(Math.max(y1, y2)), my = (ylo + yhi) >> 1;
        for (let y = ylo; y <= yhi; y++) set(x, y, 45, tg ? tg.o[1] : C.base, tg ? 200 : 130);
        set(x, my, scr.charCodeAt(0), bcol, tg ? 255 : 210);
        if (fail && tg && (st.tick % 5) < 3) set(x, my, 88, C.miss, 255);   // 失败：目标片段回弹为 X
      }
    }
    txt(HX0, 27, "GENOME STRAND  ·  LIVING", C.text, 190);
    if (at >= 0 && u < 0.78) ops.forEach((e, j) => txt(Math.max(HX0, Math.min(COLS - 11, e.tx - 4)), 28 + j, e.o[0], e.o[1], 245));   // 各片段上方错行标注操作名
    if (amp < AMAX - 0.2) aline(Math.round((laneX0 + COLS) / 2), laneY0, Math.round((laneX0 + COLS) / 2), HCy, 124, C.data, 160);  // 展开中：载波自分析器升起

    // 右侧标本舱：生成扭曲/复杂/崩坏的生体，全部失败
    for (let y = 4; y <= ROWS - 8; y++) set(DIVX, y, 124, C.base, 90);
    txt(CX0, 4, "SPECIMEN CHAMBER", C.text, 210);
    txt(CX0, 5, "SPEC #" + String(ai + 1).padStart(2, "0"), C.data, 225);
    const grow = at < 0 ? 0 : clamp((u - 0.10) / 0.40, 0, 1);
    const collapse = fail ? clamp((u - 0.78) / 0.18, 0, 1) : 0;
    const ccy = 8, NROWS = 18;
    for (let r = 0; r < NROWS; r++) { const rr = r / NROWS; if (rr > grow) continue;
      const body = 1.6 + 3.4 * Math.sin(rr * 3.1416) + fbm1(rr * 5 + seed) * 2.6;
      const shear = Math.sin(rr * 4 + seed + st.tick * 0.04) * 2.6 * (1 - collapse);
      const droop = collapse * rr * rr * 7, y = ccy + r + Math.round(droop);
      const cxr = CCX + Math.round(shear * (rr - 0.5) * 2);
      for (let d = -body; d <= body; d++) { const x = Math.round(cxr + d); if (x < CX0 || x > CX1) continue;
        const edge = Math.abs(d) > body - 1.3;
        if (collapse > 0 && bit(seed + r, (st.tick >> 2) + x) < collapse * 0.9) continue;
        const col = collapse > 0 ? C.miss : [120, 205, 150];
        const code = edge ? (d < 0 ? 40 : 41) : (fbm1(x * 0.7 + r + seed) > 0.55 ? 35 : 46);
        set(x, y, code, col, clamp((1 - collapse) * 225 + collapse * 90, 0, 255)); }
      if (r % 4 === 2 && grow > 0.4) { for (const sgn of [-1, 1]) { let lx = cxr + sgn * Math.round(body), ly = y;
        for (let k = 0; k < 4; k++) { lx += sgn; ly += Math.round((fbm1(k + seed + rr * 3) - 0.45) * 2) + (collapse > 0 ? 1 : 0);
          if (lx < CX0 || lx > CX1) break; set(lx, ly, k === 3 ? 42 : 45, collapse > 0 ? C.miss : C.base, 200); } } } }
    const verdict = at < 0 ? "AWAITING SAMPLE" : u < 0.50 ? "SYNTHESIZING..." : u < 0.78 ? "ASSAY: VIABILITY..." : "REJECT  x  FAILED";
    txt(CX0, ROWS - 9, verdict, fail ? C.miss : C.data, fail && (st.tick % 8) < 5 ? 255 : 210);
    txt(CX0, ROWS - 8, "VIABILITY 0%   FAILED " + (at >= 0 ? ai + (fail ? 1 : 0) : 0) + "/" + (at >= 0 ? ai + (fail ? 1 : 0) : 0), C.miss, 220);

    // 由①就绪环 morph 而来的错误环：与①同尺寸起步(Rx21)→缩小到 Rx8、快速平滑移到标本下方、绿√→红⊗
    const rgx = 64 + (CCX - 64) * mr, rgy = 34 + (40 - 34) * mr, rr = 21 - 13 * mr, rry = rr * 0.66;
    const rcol = mixc([80, 230, 150], [255, 92, 80], clamp(mr * 1.5, 0, 1));
    for (let k = 0; k < 84; k++) { const th = k / 84 * 6.2832; set(Math.round(rgx + Math.sin(th) * rr), Math.round(rgy - Math.cos(th) * rry), k % 5 === 0 ? 42 : 58, rcol, 235); }
    if (mr < 1) { const A = Math.round((1 - mr) * 255); aline(rgx - 5, rgy, rgx - 1.5, rgy + 3, 92, [80, 230, 150], A); aline(rgx - 1.5, rgy + 3, rgx + 5, rgy - 5, 47, [80, 230, 150], A); }
    if (mr > 0) { const A = Math.round(mr * 255); aline(rgx - rr * 0.42, rgy - rry * 0.5, rgx + rr * 0.42, rgy + rry * 0.5, 92, C.miss, A); aline(rgx - rr * 0.42, rgy + rry * 0.5, rgx + rr * 0.42, rgy - rry * 0.5, 47, C.miss, A); }

    // 底部 LOGIC ANALYZER（承接①的 CLK 信号）：一条载波展开为螺旋，其余降为低频心跳脉冲
    const lanes = [["CLK", C.clk], ["BUS", C.data], ["IRQ", C.irq], ["PIPE", C.addr]];
    lanes.forEach((ln, li) => { const y = laneY0 + li * spread; if (li > 0 && spread < 0.05) return;
      if (tt >= 25) txt(2, y, ln[0].padEnd(4), [255, 64, 52], 235);
      for (let i = laneX0 - 7; i < COLS - 8; i++) { let v; if (li === 0) v = ((st.tick * 0.12 + i) % 6 < 2); else if (li === 1) v = (Math.sin(i * 0.2 + st.tick * 0.05) > 0.2); else if (li === 2) v = fail && u < 0.82 && i > COLS - 40; else v = ((i + (st.tick >> 2)) % 9 < 3);
        set(7 + i, y, v ? 95 : 46, ln[1], v ? 220 : 55); } });
    if (tt >= 25) txt(2, laneY0 - 1, "LOGIC ANALYZER", C.text, 210);

    // 失败闪红踩在每轮尾拍；39s 阶段末一次剧烈大红屏闪，直接过渡进混乱喘息窗
    if (fail && u < 0.92) flashRGB = [255, 40, 40, (1 - (u - 0.78) / 0.14) * 0.5];
    const big = seg(tt, 38.2, 39); if (big > 0) flashRGB = [255, 20, 20, big * 0.92];
  }
  function inTgtLabel(at, u) { return at >= 0 && u < 0.55; }

  // ②.5 自我怀疑 / 喘息窗（shift 39–62）：穷举尽皆失败，机器开始质疑自身。
  //    错误环 ⊗+X 从标本舱快速平滑移回画面中心（与业力符号同位同尺寸），并被彻底淹没在噪声与故障特效中。
  function sceneDoubt(st, m) {
    const tt = ttLocal(st);
    const md = ease(clamp(seg(tt, 39, 42), 0, 1));               // 环移回中心（快且平滑）
    const reorg = seg(tt, 57, 62);                               // 整理思绪：串行清屏重显示
    const dn = seg(tt, 39, 42) * (1 - reorg * 0.85);             // 混乱密度：涌入、reorg 期收束
    const clearY = reorg * (ROWS + 8);                           // 自上而下的清屏前沿
    const cx = 64, cy = HEART.y, rr = 8 + 13 * md, rry = rr * 0.66;
    const jx = (fbm1(st.tick * 0.7) - 0.5) * 6 * dn, jy = (fbm1(st.tick * 0.9 + 5) - 0.5) * 3 * dn;   // 抖动
    const rcx = cx + (1 - md) * 0 + jx, rcy = cy + jy;             // 到位后停在中心并抖动

    // 全屏静态噪声雪（淹没一切，但在错误环周围留出清明区）
    const NS = Math.round(dn * 1050), GS = "#%&@*+=:.<>|/\\^~";
    for (let i = 0; i < NS; i++) { const x = (bit(st.tick * 13 + i, 1) * COLS) | 0, y = (bit(st.tick * 7 + i, 2) * ROWS) | 0;
      if (y < clearY) continue;                                    // reorg：清屏前沿之上的噪声被抹去
      const dx = (x - cx) / rr, dy = (y - cy) / rry; if (md > 0.6 && dx * dx + dy * dy < 1.7) continue;
      const ch = GS.charCodeAt((bit(i, (st.tick >> 1)) * GS.length) | 0);
      const col = bit(i, 3) < 0.55 ? C.miss : (bit(i, 4) < 0.5 ? C.clk : C.data);
      set(x, y, ch, col, Math.round(55 + bit(i, 5) * 105)); }
    // 水平撕裂故障带
    for (let b = 0; b < 7; b++) { const by = (bit(st.tick * 3 + b, 9) * ROWS) | 0; if (bit(b, st.tick >> 3) < 0.5) continue;
      const off = ((bit(st.tick + b, 4) - 0.5) * 16 * dn) | 0; const bright = bit(b, st.tick) < 0.4;
      for (let x = 0; x < COLS; x++) set(x, by, bright ? 61 : 45, bright ? C.clk : C.miss, Math.round(95 * dn));
      for (let x = 0; x < COLS; x++) { const sx = x + off; if (sx < 0 || sx >= COLS) continue; if (bit(x, b + st.tick) < 0.12) set(x, by, 35, C.data, Math.round(150 * dn)); } }

    // 错误环 ⊗+X（占据业力符号位，留出清明区后作为焦点；X 随噪声抖动旋转、脉冲）
    const rot = (fbm1(st.tick * 0.5) - 0.5) * 0.8 * dn, pulse = 0.82 + 0.18 * Math.sin(st.tick * 0.4);
    const hotr = [255, 150, 140], ringc = [255, 210, 200];
    for (let k = 0; k < 150; k++) { const th = k / 150 * 6.2832; const jr = rr + (bit(k, st.tick) - 0.5) * 4 * dn;
      for (const rrk of [1, 0.9]) { const px = Math.round(rcx + Math.sin(th) * jr * rrk), py = Math.round(rcy - Math.cos(th) * rry * (jr / rr) * rrk);
        set(px, py, k % 3 === 0 ? 42 : 58, rrk === 1 ? ringc : hotr, Math.round((rrk === 1 ? 255 : 200) * pulse)); } }
    const ax = rr * 0.44 * Math.cos(rot), ay = rry * 0.52 * Math.sin(rot + 1.2), bl = (st.tick % 7) < 4 ? 255 : 120;
    aline(rcx - ax, rcy - ay, rcx + ax, rcy + ay, 92, hotr, Math.round(255 * pulse)); aline(rcx - ax, rcy + ay, rcx + ax, rcy - ay, 47, hotr, Math.round(255 * pulse));
    aline(rcx - ax, rcy - ay, rcx + ax, rcy + ay, 92, [255, 235, 225], bl); aline(rcx - ax, rcy + ay, rcx + ax, rcy - ay, 47, [255, 235, 225], bl);

    // 自我诊断文本（故障闪烁）
    const msgs = ["EXHAUSTIVE SEARCH  ::  0 VIABLE", "SPECIMEN MORTALITY  ::  100%", "MODEL DOUBTING WORLD", "RECURSION UNRESOLVED", "IS THE ANSWER REAL ?", "TRIPLE AFFIRMATION ... ?"];
    txt(2, 0, "RANDOM GODS · ITERATOR CORE — SELF-DIAGNOSIS / DOUBT", C.miss, 235);
    const mi = ((tt - 39) / 2.2 | 0) % msgs.length;
    for (let k = 0; k < 3; k++) { const s = msgs[(mi + k) % msgs.length]; const gx = ((bit(st.tick + k, 6) - 0.5) * 6 * dn) | 0;
      txt(2 + gx, 2 + k * 2, s, k === 0 ? C.clk : C.miss, Math.round((k === 0 ? 230 : 150) * (0.6 + 0.4 * dn))); }
    txt(COLS - 30, 0, "ENTROPY " + Math.round((0.5 + 0.5 * dn) * 100) + "%", C.miss, 240);
    txt(COLS - 30, 2, "STABILITY " + Math.round((1 - dn) * 100) + "%", C.data, 220);
    txt(COLS - 30, 4, "ATTEMPTS FAILED  6 / 6", C.miss, 220);
    txt(COLS - 20, 6, "T+" + tt.toFixed(1) + "s", C.dim, 190);

    // 底部分析器：走线失控
    const lanes = [["CLK", C.clk], ["BUS", C.data], ["IRQ", C.irq], ["PIPE", C.addr]];
    const laneBase = ROWS - 6;
    lanes.forEach((ln, li) => { const y = laneBase + li; txt(2, y, ln[0].padEnd(4), [255, 64, 52], 235);
      for (let i = 0; i < COLS - 8; i++) { const v = bit(i + li * 31, st.tick >> (li === 0 ? 1 : 0)) < (0.3 + 0.4 * dn);
        set(7 + i, y, v ? 95 : 46, ln[1], v ? Math.round(120 + 120 * dn) : 55); } });
    txt(2, laneBase - 1, "LOGIC ANALYZER  //  UNSTABLE", C.text, 210);

    // 整理思绪：自上而下的刷新扫描线（串行清屏前沿），并浮现重振文本
    if (reorg > 0) { const sy = Math.round(clearY);
      for (let x = 0; x < COLS; x++) { set(x, sy, 61, C.clk, 255); set(x, sy - 1, 45, C.data, 150); set(x, sy + 1, 45, C.data, 90); }
      txt(Math.round(COLS / 2) - 11, 20, "REORGANIZING THOUGHTS", C.clk, Math.round(180 * reorg + 60));
      txt(Math.round(COLS / 2) - 11, 21, "REBUILDING WORLD MODEL", C.data, Math.round(170 * reorg + 40)); }
  }

  // ②→混乱 的崩解：把已渲染的有序 ASCII 结构整体"碎开、垮落、变成乱码"（纯函数逐帧，读快照后重映射）
  function shatterGrid(st, k) {
    const sCh = gCh.slice(), sR = gR.slice(), sG = gG.slice(), sB = gB.slice(), sA = gA.slice();
    gCh.fill(32); gA.fill(0);
    const NOISE = "01#%&@*+=:.<>/\\|^~";
    for (let p = 0; p < N; p++) { const a = sA[p]; if (a < 10) continue; const x = p % COLS, y = (p / COLS) | 0;
      const fall = Math.round(k * k * ROWS * 0.95 * (0.35 + bit(p, st.tick >> 1) * 0.9) + k * bit(p + 7, st.tick) * 7);   // 重力垮落
      const nx = x + Math.round((bit(p + 3, st.tick) - 0.5) * k * 9), ny = y + fall;
      if (ny >= ROWS || nx < 0 || nx >= COLS) continue;
      let ch = sCh[p], col = [sR[p], sG[p], sB[p]], na = a * (1 - k * 0.45);
      if (bit(p + 11, st.tick) < k * 0.85) { ch = NOISE.charCodeAt((bit(p, st.tick) * NOISE.length) | 0); col = bit(p + 2, st.tick) < 0.5 ? C.miss : C.data; }   // 碎成乱码
      const q = ny * COLS + nx; if (na > gA[q]) { gCh[q] = ch; gR[q] = col[0]; gG[q] = col[1]; gB[q] = col[2]; gA[q] = na; } }
  }
  function collapseFlash(tt) {   // ②→混乱的大红屏闪：39s 达峰、随后随崩解一同退去
    if (tt < 38.2 || tt >= 41.2) return;
    const rf = tt < 39 ? seg(tt, 38.2, 39) : 1 - seg(tt, 39, 41.2);
    flashRGB = [255, 20, 20, rf * 0.9];
  }

  // ①→② 的字符阵变换：②布局用 1s 从一片青色乱码中"解码显形"（省去缓慢位移）
  function scrambleIn(st, mat) {
    const NOISE = "#%&@*+=:.<>|/\\^~01";
    for (let p = 0; p < N; p++) { if (mat >= bit(p, 7)) continue;
      gCh[p] = NOISE.charCodeAt((bit(p, st.tick >> 1) * NOISE.length) | 0); gR[p] = C.data[0]; gG[p] = C.data[1]; gB[p] = C.data[2]; gA[p] = Math.max(gA[p], 120); }
  }

  // 腐化侵蚀：以心脏为圆心向外扩散的腐蚀前沿（变色紫+抖动+蚕食）+ 底部上升的紫液池，逐格吞噬各运算部件
  function corrodeGrid(st, cor) {
    if (cor <= 0) return;
    const cx = HEART.x, cy = HEART.y, purp = [150, 60, 220];
    const R = ease(cor) * (Math.max(COLS, ROWS * 1.9) + 20);   // 腐蚀半径（cell 近似方形，y 乘 1.9）
    const poolTop = ROWS - ease(cor) * (ROWS * 0.72);          // 底部紫液池上升
    const sCh = gCh.slice(), sR = gR.slice(), sG = gG.slice(), sB = gB.slice(), sA = gA.slice();
    gCh.fill(32); gA.fill(0);
    for (let p = 0; p < N; p++) { const a = sA[p]; if (a < 10) continue; const x = p % COLS, y = (p / COLS) | 0;
      const d = Math.hypot(x - cx, (y - cy) * 1.9), hit = d < R || y >= poolTop;
      if (!hit) { gCh[p] = sCh[p]; gR[p] = sR[p]; gG[p] = sG[p]; gB[p] = sB[p]; gA[p] = sA[p]; continue; }
      if (bit(p, st.tick) < cor * 0.2) continue;   // 蚕食：少量格被吃掉（克制，别糊成噪点）
      const jx = Math.round((bit(p + 1, st.tick) - 0.5) * cor * 3), jy = Math.round((bit(p + 2, st.tick) - 0.5) * cor * 2);
      const nx = clamp(x + jx, 0, COLS - 1) | 0, ny = clamp(y + jy, 0, ROWS - 1) | 0, q = ny * COLS + nx;
      const na = a * (1 - cor * 0.2), col = mixc([sR[p], sG[p], sB[p]], purp, 0.5);
      if (na > gA[q]) { gCh[q] = sCh[p]; gR[q] = col[0]; gG[q] = col[1]; gB[q] = col[2]; gA[q] = na; } }
    // 液池：黏稠拉丝的紫液体——fbm 驱动的起伏液面 + 垂挂拉丝 + 体内致密填充（不再规整正弦）
    const pt = poolTop;
    for (let x = 0; x < COLS; x++) {
      const n1 = fbm1(x * 0.12 + st.tick * 0.04) - 0.5, n2 = fbm1(x * 0.35 + st.tick * 0.09 + 7) - 0.5;
      const surf = pt + n1 * 4.5 + n2 * 2.2;   // 不规则液面
      const strand = bit(x, 3) < 0.18 ? (2 + bit(x, 9) * 5) : 0;   // 拉丝：部分位置垂下细丝
      for (let y = Math.ceil(surf - strand); y < ROWS; y++) {
        const dep = Math.max(0, (y - pt) / (ROWS - pt + 1));
        const ch = y < surf ? ":" : (y - surf < 1.2 ? "~" : ".");   // 拉丝段用 ':'，表层 '~'，体内 '.'
        set(x, y, ch.charCodeAt(0), mixc([205, 130, 255], [60, 12, 110], dep), Math.round((230 - dep * 60) * (y < surf ? 0.75 : 1))); } }
    for (let x = 0; x < COLS; x++) { const n1 = fbm1(x * 0.12 + st.tick * 0.04) - 0.5, n2 = fbm1(x * 0.35 + st.tick * 0.09 + 7) - 0.5;
      set(x, Math.round(pt + n1 * 4.5 + n2 * 2.2) - 1, 61, [225, 175, 255], 240); }   // 液面高光
  }

  // ③：DNA 于同高度横贯全屏，并以彻底混乱的方式随机重组（每帧碱基乱跳 + 交叉互换）
  function drawDna3(st, m) {
    const HCy = 35, twist = 0.52, f = st.tick;
    const RED = [255, 50, 70], PUR = [150, 60, 230];
    for (let x = 0; x < COLS; x++) {
      const chaos = Math.sin(x * 0.6 + f * 0.25) * 1.3;                 // 混乱相位扰动
      const s = Math.sin(x * twist + f * 0.14 + chaos);
      const a = 3.2 * (0.6 + 0.8 * Math.abs(fbm1(x * 0.25 + f * 0.06) - 0.5) * 2);
      const y1 = HCy + a * s, y2 = HCy - a * s;
      const rc = mixc(RED, PUR, 0.5 + 0.5 * Math.sin(x * 0.7 + f * 0.45));   // 激烈变化的红↔紫
      set(x, Math.round(y1), 46, rc, 235); set(x, Math.round(y2), 46, rc, 235);
      if (x % 2 === 0) {
        const b = "ATGC"[(bit(x, f >> 1) * 4 | 0) & 3];                     // 每帧随机跳＝彻底混乱重组（索引取模防 bit()=1 越界）
        const ylo = Math.round(Math.min(y1, y2)), yhi = Math.round(Math.max(y1, y2)), my = (ylo + yhi) >> 1;
        for (let y = ylo; y <= yhi; y++) set(x, y, 45, mixc(rc, PUR, 0.4), 140);
        set(x, my, b.charCodeAt(0), rc, 255);
        if (bit(x + 5, f) < 0.05) { set(x, my - 1, 47, PUR, 255); set(x, my + 1, 92, RED, 255); }   // 交叉互换
      }
    }
    txt(2, HCy - 6, "GENOME RECOMBINATION  //  CHAOTIC REASSEMBLY", C.text, 180);
  }


  function fill(st, m) {
    gCh.fill(32); gR.fill(0); gG.fill(0); gB.fill(0); gA.fill(0); flashRGB = null; clipMinY = 0; clipMaxY = 1e9; introY = 1e9;
    const tt = st.tick / pack.fps;
    if (tt < bootEnd) { sceneBoot(st, m); return; }              // ① 苏醒 POWER-ON
    const shatterK = seg(tt, 38, 41);                            // ②→混乱：有序结构碎开垮落成乱码
    if (tt < bioEnd) { sceneBio(st, m); if (tt < 23) scrambleIn(st, seg(tt, 22, 23)); if (shatterK > 0) shatterGrid(st, shatterK); collapseFlash(tt); return; }   // ② 生物工程（chorus 22–39）
    if (tt < sceneStart) { if (shatterK > 0 && shatterK < 1) { sceneBio(st, m); shatterGrid(st, shatterK); } sceneDoubt(st, m); collapseFlash(tt); return; }   // ②.5 自我怀疑（shift 39–62）
    // ③ 入场：刷新前沿之上=乱序CPU+金色心；之下=仍待改写的红 ⊗+X 与残余噪声（逐行改写，不硬切）
    introY = (tt < sceneStart + 2.6) ? ((tt - sceneStart) / 2.6) * (ROWS + 3) : 1e9;
    clipMinY = 0; clipMaxY = introY;
    // HUD + 语法图例
    txt(2, 0, "RANDOM GODS · ITERATOR CORE — OUT-OF-ORDER BIOCPU", C.text, 255);
    txt(2, 1, "LOAD " + (m.load * 100 | 0) + "%  BUS " + (m.busUtil * 100 | 0) + "%  ALU " + (m.alu * 100 | 0) + "%  HIT " + (m.hitRate * 100 | 0) + "%  RET " + m.retired, C.data, 235);
    txt(COLS - 24, 1, "ENTROPY " + (m.entropy * 100 | 0) + "%", C.irq, 235);
    if (st.slow > 0) txt(COLS - 26, 0, "* SLOW-MO *", C.miss, 255);
    txt(2, 2, "addr", C.addr, 235); txt(8, 2, "data", C.data, 235); txt(14, 2, "ctrl", C.ctrl, 235); txt(20, 2, "irq", C.irq, 235); txt(25, 2, "clk", C.clk, 235);

    // 腐化进度（146→192.3）：三重肯定变紫扭曲滴落、紫液在下方堆积、腐蚀前沿自心脏向外吞噬各部件，POWER 最后倒下
    const cor = seg(tt, climaxEnd, powerEnd);
    const purp = [150, 60, 220];
    const pwr = m.power * (1 - cor);   // 电力被腐化蚕食
    txt(COLS - 30, 2, "POWER", cor > 0.8 ? purp : C.addr, 235);
    for (let i = 0; i < 12; i++) { const lit = i < Math.round(pwr * 12); const eaten = cor > 0.8 && bit(i, st.tick >> 2) < (cor - 0.8) * 5;
      set(COLS - 23 + i, 2, lit ? 61 : 45, eaten ? purp : (lit ? C.addr : C.dim), lit ? 245 : 70); }

    // 流水线 5 级（FETCH/WB 带实质内容与动效）
    STAGES.forEach((s, i) => { const ins = st.pipe[i]; const p = NP[s]; box(p[0], p[1], 20, 5, ins ? C.clk : C.base, s, ins ? 240 : 110);
      if (s === "FETCH") {
        txt(p[0] - 9, p[1] - 1, "PC " + st.pc.toString(16).toUpperCase().padStart(6, "0"), C.data, 245);
        for (let q = 0; q < 6; q++) { const op = cpu.OPS[(st.tick + q * 7) % cpu.OPS.length]; const on = ((st.tick >> 1) % 6) === q; txt(p[0] - 9 + q * 3, p[1] + 1, op.slice(0, 2), on ? C.clk : C.dim, on ? 255 : 140); }
      } else if (s === "WB") {
        txt(p[0] - 9, p[1] - 1, "RET " + st.retired, C.data, 245);
        if (ins) txt(p[0] - 9, p[1] + 1, ">" + st.rnames[ins.rd] + "=" + (st.regs[ins.rd] & 255).toString(16).toUpperCase().padStart(2, "0"), C.clk, 255);
      } else if (ins) txt(p[0] - 8, p[1] + 1, ins.op.padEnd(6) + "#" + ins.id, C.data, 240); });
    // ALU 进位链
    const ay = NP.EXEC[1] + 3; txt(NP.EXEC[0] - 9, ay, "CARRY ", C.dim, 200);
    for (let i = 0; i < 8; i++) { const on = bit(st.tick, i) < m.alu; set(NP.EXEC[0] - 2 + i, ay, on ? 35 : 46, on ? [255, 170 - i * 12, 40] : C.dim, on ? 245 : 90); }

    // 总线轨道（占用率）
    const by = NP.BUS[1]; txt(2, by - 1, "BUS util " + (m.busUtil * 100 | 0) + "%  queue " + m.queue, C.text, 220);
    for (let x = 2; x < COLS - 2; x++) { const u = (x - 2) / (COLS - 4); const busy = u < m.busUtil; set(x, by, busy ? 61 : 45, busy ? C.data : C.base, busy ? 230 : 80); }

    // 四个功能组件（对齐一行 + 各自外观 + IO 口）
    for (const k in BLK) { const b = BLK[k]; const r = box(b.x, b.y, b.w, b.h, b.bc, { IRQ: "INTERRUPTS", REG: "REGISTERS", CACHE: "CACHE", DRAM: "DRAM/IO" }[k], (k === "IRQ" && st.irqActive) ? 255 : 175);
      b.port = { x: b.x, y: r.y1 }; styleComponent(k, st, m, r); }

    // 计算之心已移到毛玻璃背景层（见 draw）

    // 在途信息流：骑在总线轨道上（辉光头 + 短拖尾）
    for (const fl of st.flows) { const key = fl.path.join(""); let hh = 0; for (let i = 0; i < key.length; i++) hh = (hh * 31 + key.charCodeAt(i)) | 0; const x = 2 + (((Math.abs(hh) + st.tick * 15) % (COLS - 4))); const col = FC[fl.kind], a = clamp(255 - fl.age * 25, 60, 255);
      set(x, by, 62, col, a); set(x - 1, by, 45, col, a * 0.55); set(x - 2, by, 45, col, a * 0.28); }

    // 指令预取队列 → 四组件：细线迹 + 沿线辉光信息（带拖尾），乱中有序
    const qy = 8, comps = Object.keys(BLK), slots = 8, rot = (st.tick / 8) | 0;
    txt(2, qy - 1, "PREFETCH QUEUE", C.text, 200);
    for (let s = 0; s < slots; s++) {
      const x = 18 + s * 13, dest = BLK[comps[(s + rot) % comps.length]], tx = dest.x, ty = dest.y - 5;
      const n = Math.max(2, Math.round(Math.max(Math.abs(tx - x), Math.abs(ty - qy)) * 1.4));
      for (let i = 0; i <= n; i++) { const u = i / n; set(x + (tx - x) * u, (qy + 1) + (ty - qy - 1) * u, 46, C.base, 70); }   // 细线
      set(x, qy, 45, C.data, 180);
      const col = s % 3 === 0 ? C.addr : C.data;
      for (let k = 0; k < 6; k++) { const u = ((st.tick * 0.22 + s * 0.17) % 1) - k * 0.04; if (u < 0 || u > 1) continue;   // 辉光头 + 彗尾
        set(x + (tx - x) * u, (qy + 1) + (ty - qy - 1) * u, k === 0 ? 62 : 42, col, clamp(255 - k * 42, 0, 255)); }
      set(tx, ty, 93, C.base, 200);
    }

    // ③：全宽混乱重组的 DNA（横贯屏幕，同高度）
    drawDna3(st, m);

    // 终极答案：艺术大字本身即进度条（TRIPLE AFFIRMATION / 三重肯定），飞字不断组装，断电前永不填满
    const ANSWER = "TRIPLE AFFIRMATION";
    const gy = ROWS - 15, gx0 = Math.round((COLS - ANSWER.length * 6) / 2);
    const progress = clamp((tt - sceneStart) / (climaxEnd - sceneStart), 0, 1);   // 62s→146s 铺满
    const revealed = Math.round(progress * ANSWER.length);
    txt(gx0, gy - 1, "ULTIMATE ANSWER  ·  TRIPLE AFFIRMATION", C.text, 210);
    let fx = gx0, fy = gy + 2;
    for (let li = 0; li < ANSWER.length; li++) {
      const g = GLYPH[ANSWER[li]] || GLYPH[" "]; const built = li < revealed, frontier = li === revealed;
      for (let r = 0; r < 5; r++) for (let c = 0; c < 5; c++) {
        if (g[r][c] !== "1") continue; let x = gx0 + li * 6 + c, y = gy + r;
        if (built && cor > 0) { y += Math.round(Math.sin(x * 0.5 + st.tick * 0.25) * cor * 3); x += Math.round(Math.cos(y * 0.7 + st.tick * 0.2) * cor * 2); }   // 扭曲
        if (built) set(x, y, 35, cor > 0 ? mixc(C.data, purp, cor) : C.data, 255);
        else if (frontier) { const on = bit(st.tick, li * 5 + r * 3) < 0.55; set(x, y, on ? 35 : 43, C.clk, on ? 255 : 150); }
        else set(x, y, 46, C.dim, 95);
      }
      if (built && cor > 0) { const bx = gx0 + li * 6 + 2, by = gy + 5, dl = cor * 9 * (0.5 + bit(li, 3));   // 大字下缘垂落紫黏丝
        for (let k = 0; k < dl; k++) set(bx + Math.round(Math.sin(k * 0.6 + st.tick * 0.3) * cor * 1.5), by + k, k >= dl - 1 ? "o".charCodeAt(0) : 58, purp, Math.round(220 * (1 - k / (dl + 2)))); }
      if (frontier) { fx = gx0 + li * 6 + 2; fy = gy + 2; }
    }
    if (revealed >= ANSWER.length) { const cw = "C O R R U P T I O N"; txt(Math.round((COLS - cw.length) / 2), gy + 6, cw, mixc(purp, [225, 175, 255], 0.5 + 0.5 * Math.sin(st.tick * 0.3)), 255); }   // 走完不显"完成"，而显"腐化"：下方居中一行
    // 飞出的字符：解析流（可 seek），加速汇聚到正在组装的前沿字
    for (const k in BLK) { const b = BLK[k]; const col = b.col === "irq" ? C.irq : b.col === "addr" ? C.addr : C.data; const interval = 4;
      for (let j = 0; j < 11; j++) { const n = Math.floor(st.tick / interval) - j; if (n < 0) continue; const age = st.tick - n * interval; const life = 24; if (age >= life) continue; const u = age / life;
        const x = b.x + (fx - b.x) * u * u, y = (b.y + 6) + (fy - b.y - 6) * u;
        set(x, y, "0123456789ABCDEF".charCodeAt((n * 7 + b.x + j * 3) & 15), col, clamp((1 - u) * 235, 0, 255)); } }

    // 逻辑分析仪波形轨
    const ly = ROWS - 6; txt(2, ly - 1, "LOGIC ANALYZER", C.text, 220);
    const lanes = [["CLK", C.clk], ["BUS", C.data], ["IRQ", C.irq], ["PIPE", C.addr]];
    lanes.forEach((ln, li) => { const y = ly + li; txt(2, y, ln[0].padEnd(4), [255, 64, 52], 255);
      for (let i = 0; i < COLS - 8; i++) { let v; if (li === 0) v = ((st.tick + i) % 4 < 2); else if (li === 1) v = (st.busHist[st.busHist.length - (COLS - 8) + i] || 0) > 0; else if (li === 2) v = st.irqActive ? i > COLS - 20 : bit(st.tick, i + 7) < 0.05; else v = m.inflight > (i % 5);
        set(7 + i, y, v ? 95 : 46, ln[1], v ? 235 : 70); } });

    st.events.slice(-3).forEach((e, i) => txt(COLS - 40, 25 + i, e.s.slice(0, 38), /MISS|MISPRED/.test(e.s) ? C.miss : C.irq, 235));

    corrodeGrid(st, cor);   // 腐化：紫色侵蚀前沿自心脏向外吞噬各部件 + 底部液池

    // 刷新前沿之下：仍渲染②.5 的红 ⊗+X 与残余噪声，随扫描线推进被逐行改写成金色业力符号
    if (introY < 1e9) { clipMinY = Math.floor(introY); clipMaxY = 1e9; sceneDoubt(st, m); clipMinY = 0; }
    clipMaxY = 1e9;
  }

  function nodePos(name) { if (NP[name]) return NP[name]; if (BLK[name]) return [BLK[name].x, BLK[name].y]; if (name === "CACHE") return [BLK.CACHE.x, BLK.CACHE.y]; return null; }

  function styleComponent(k, st, m, r) {
    if (k === "REG") { st.regs.forEach((v, i) => { const rx = r.x0 + 1 + (i % 4) * 7, ry = r.y0 + 2 + ((i / 4) | 0) * 2;
      txt(rx, ry, st.rnames[i].slice(0, 3), C.dim, 200); txt(rx + 3, ry, v.toString(16).toUpperCase().padStart(4, "0"), bit(st.tick, i + 20) < 0.5 ? C.data : C.text, 240); });
      ["Z", "C", "S", "O"].forEach((f, i) => txt(r.x0 + 1 + i * 7, r.y1 - 1, f + "=" + st.flags[f], st.flags[f] ? C.clk : C.dim, 230)); }
    else if (k === "CACHE") { const cop = st.cop;
      for (let s = 0; s < st.sets; s++) for (let w = 0; w < st.ways; w++) { const L = st.cache[s * st.ways + w]; const x = r.x0 + 2 + w * 5, y = r.y0 + 2 + s * 2;
        let col = L.valid ? C.hit : C.dim, a = L.valid ? 210 : 60, code = L.valid ? 86 : 46;
        if (cop && cop.index === s) {
          if (cop.phase === 1) { const bl = bit(st.tick, s * 4 + w) < 0.5; col = bl ? C.clk : C.addr; a = bl ? 255 : 140; code = 63; }
          else if (cop.phase >= 2 && !cop.miss && cop.way === w) { col = C.hit; a = 255; code = 35; }
          else if (cop.miss && cop.victim === w && cop.phase >= 3) { col = C.miss; a = 255; code = 37; }
          else { col = C.base; a = 110; }
        }
        set(x, y, code, col, a); set(x + 1, y, L.valid ? 86 : 46, col, a * 0.6);
        if (L.dirty) set(x + 3, y, 68, C.addr, 240); }
      txt(r.x0 + 1, r.y1 - 1, cop ? ("tag" + (cop.tag & 15).toString(16) + " idx" + cop.index + " off" + cop.offset + (cop.miss ? " MISS" : " HIT")) : ("hit " + (m.hitRate * 100 | 0) + "%"), cop && cop.miss ? C.miss : C.data, 235); }
    else if (k === "IRQ") { st.irqPend.slice(0, 4).forEach((q, i) => { const y = r.y0 + 2 + i; txt(r.x0 + 1, y, q.n.padEnd(5), C.irq, 230); for (let p = 0; p < q.p; p++) set(r.x0 + 7 + p, y, 61, C.irq, 220); });
      if (st.irqActive) { txt(r.x0 + 1, r.y1 - 2, "> " + st.irqActive.n, C.clk, 255); txt(r.x0 + 1, r.y1 - 1, "STACK " + "#".repeat(Math.min(8, st.stack.length)), C.clk, 220); } }
    else if (k === "DRAM") { const d = st.dram, act = d.cmd === "ACT" || d.cmd === "RD" || d.cmd === "WR";
      for (let bn = 0; bn < 4; bn++) { const x = r.x0 + 2 + bn * 4, hot = act && bn === (d.bank | 0); for (let y = r.y0 + 2; y <= r.y1 - 3; y++) set(x, y, 124, hot ? C.addr : C.base, hot ? 240 : 130); }
      txt(r.x0 + 1, r.y0 + 2, "RB", C.dim, 200); txt(r.x0 + 3, r.y0 + 2, d.row < 0 ? "--" : (d.row & 255).toString(16).toUpperCase().padStart(2, "0"), d.row >= 0 ? C.addr : C.dim, 240);
      txt(r.x0 + 1, r.y1 - 2, d.cmd + " " + d.t, d.cmd === "REF" ? C.irq : d.cmd === "IDLE" ? C.dim : C.data, 250);
      if (d.cmd === "RD" || d.cmd === "WR") for (let c = 0; c < 3; c++) { const u = ((st.tick * 0.3 + c * 0.3) % 1); set(r.x0 + 2 + c * 4, r.y0 + 3 + u * (r.y1 - r.y0 - 5), 62, d.cmd === "WR" ? C.addr : C.data, 255 * (1 - u)); }
      if (d.cmd === "REF") txt(r.x0 + 1, r.y1 - 1, "REF " + d.refT, C.irq, 250); }
  }

  // 底部频谱柱（画到离屏背景层，随雨一起毛玻璃虚化，被前景分析器/大字压住）
  function drawSpectrum(g2, st) {
    const fs = Math.max(6, Math.floor(chh * 0.9)); g2.font = `${fs}px ${FONT}`; g2.textAlign = "center"; g2.textBaseline = "alphabetic";
    const base = ROWS - 1, bandH = 13, f = clamp(st.tick, 0, pack.T - 1);
    for (let x = 0; x < COLS; x++) {
      const b = Math.min(pack.NB - 1, Math.floor(x / COLS * pack.NB));
      const e = clamp(pack.band(b, f) * 1.6, 0, 1), h = Math.round(e * bandH);
      for (let k = 0; k < h; k++) { const y = base - k; g2.fillStyle = `rgba(72,175,210,${clamp((1 - k / bandH) * 0.92, 0, 0.95)})`;
        g2.fillText(k === h - 1 ? "_" : "|", ox + (x + 0.5) * cw, oy + (y + 0.82) * chh); }
    }
  }

  // 计算之心 = 金色"⊗"（十级业力符号），画到毛玻璃背景层 → 前景后面一团柔光，随音频微闪
  function drawHeart(g2, st, m, clipY) {
    const fs = Math.max(6, Math.floor(chh * 0.9)); g2.font = `${fs}px ${FONT}`; g2.textAlign = "center"; g2.textBaseline = "alphabetic";
    const cy2 = clipY === undefined ? 1e9 : clipY;
    const put = (col, row, ch, rgb, a) => { if (row > cy2) return; g2.fillStyle = `rgba(${rgb[0] | 0},${rgb[1] | 0},${rgb[2] | 0},${clamp(a / 255, 0, 1)})`; g2.fillText(ch, ox + (col + 0.5) * cw, oy + (row + 0.82) * chh); };
    const cx = HEART.x, cy = HEART.y, Rx = Math.min(COLS * 0.17, 21), Ry = Rx * 0.66;
    const tt = st.tick / pack.fps, corrupt = seg(tt, climaxEnd, climaxEnd + 4);   // 高潮结束→业力符号转紫、变黏液滴落
    let gold = [255, 210, 105], hot = [255, 250, 222];
    if (corrupt > 0) { gold = mixc(gold, [150, 60, 220], corrupt); hot = mixc(hot, [215, 150, 255], corrupt); }
    const pulse = clamp(0.8 + 0.2 * m.load, 0, 1) * clamp(0.4 + 0.6 * m.power, 0, 1);
    const flick = 0.85 + 0.15 * Math.sin(st.tick * 0.5);
    for (let i = 0; i < 130; i++) { const a = i / 130 * 6.283, ca = Math.cos(a), sa = Math.sin(a);
      put(cx + ca * (Rx + 2.5), cy + sa * (Ry + 1.6), ".", gold, 175 * pulse);
      put(cx + ca * Rx, cy + sa * Ry, i % 6 < 3 ? "*" : ":", gold, 255 * pulse * flick); }
    for (let t = 0; t <= 1.001; t += 0.02) {
      const xa = cx - Rx * 0.72 + Rx * 1.44 * t, ya = cy - Ry * 0.72 + Ry * 1.44 * t;
      const yb = cy + Ry * 0.72 - Ry * 1.44 * t;
      for (const [px, py, cc] of [[xa, ya, "\\"], [xa, yb, "/"]]) {
        put(px, py, cc, hot, 255 * pulse * flick);
        put(px + 1, py, ".", gold, 150 * pulse); put(px - 1, py, ".", gold, 150 * pulse);
        put(px, py + 1, ".", gold, 140 * pulse); put(px, py - 1, ".", gold, 140 * pulse);
        put(px + 1, py + 1, ".", gold, 70 * pulse); put(px - 1, py - 1, ".", gold, 70 * pulse);
      } }
    put(cx, cy, "*", hot, 255 * pulse);
    // 日珥/日冕：贴环的 fbm streamer + 环状喷发弧（借 The Sun Station 算法，椭圆度量匹配 ⊗）
    const corR = Rx * 1.85, span = corR / Rx - 1;
    for (let r = Math.floor(cy - corR * 0.66); r <= Math.ceil(cy + corR * 0.66); r++) for (let c = Math.floor(cx - corR); c <= Math.ceil(cx + corR); c++) {
      const ex = (c - cx) / Rx, ey = (r - cy) / Ry, rr = Math.hypot(ex, ey);
      if (rr <= 0.98 || rr > corR / Rx) continue;
      const ang = Math.atan2(ey, ex);
      const strm = 0.5 + 0.5 * Math.sin(ang * 5 + fbm1(ang * 1.8 + st.tick * 0.02) * 4);
      const streamer = 0.4 + 0.6 * strm, h = (rr - 1) / span;
      let v = Math.exp(-h * 5.5) * (0.5 + 0.5 * streamer) + Math.pow(Math.max(0, 1 - h / 0.9), 1.7) * Math.pow(streamer, 2.2);
      v *= pulse * (0.55 + 0.45 * m.load);
      if (v > 0.05) put(c, r, v > 0.55 ? "*" : (v > 0.28 ? "+" : "."), v > 0.5 ? hot : gold, clamp(v * 255, 0, 255));
    }
    // 腐化：黏液自环的下缘不断滴落（原位、原背景层）
    if (corrupt > 0) { const drip = Math.max(0, tt - climaxEnd), ND = 9;
      for (let i = 0; i < ND; i++) { const ang = Math.PI * (0.12 + 0.76 * i / (ND - 1));
        const bx = cx + Math.cos(ang) * Rx, by = cy + Math.sin(ang) * Ry, ph = bit(i, 3);
        const maxL = ROWS - by - 1, len = Math.min(maxL, drip * (1.4 + ph * 2.2));
        for (let k = 0; k <= len; k++) { const wob = Math.sin(k * 0.5 + tt * 3 + i) * (0.5 + corrupt * 0.8);
          put(bx + wob, by + k, k >= len ? "o" : (k % 3 === 0 ? ":" : "."), gold, 220 * (1 - k / (len + 4))); }
        const fall = (drip * (2.2 + ph * 3) + ph * maxL) % (maxL + 5);   // 反复坠落的滴珠
        put(bx + Math.sin(fall * 0.4) * 0.8, by + fall, "*", mixc(gold, [225, 170, 255], 0.5), 255 * (1 - fall / (maxL + 5))); } }
  }

  // ① 加载环：与业力符号同位同尺寸，画在毛玻璃背景层（进度金弧 + 旋转 spinner；完成→绿环 + 闪烁 √）
  function drawLoader(g2, st) {
    const fs = Math.max(6, Math.floor(chh * 0.9)); g2.font = `${fs}px ${FONT}`; g2.textAlign = "center"; g2.textBaseline = "alphabetic";
    const put = (col, row, ch, rgb, a) => { g2.fillStyle = `rgba(${rgb[0] | 0},${rgb[1] | 0},${rgb[2] | 0},${clamp(a / 255, 0, 1)})`; g2.fillText(ch, ox + (col + 0.5) * cw, oy + (row + 0.82) * chh); };
    const cx = HEART.x, cy = HEART.y, Rx = Math.min(COLS * 0.17, 21), Ry = Rx * 0.66;
    const tt = st.tick / pack.fps, ob = seg(tt, 0, BOOT.boot[1]), done = tt >= BOOT.boot[1];
    const gold = [255, 210, 105], hot = [255, 250, 222], cyan = C.data, green = C.hit, base = C.base;
    const NST = 210, head = (st.tick * 0.14) % 6.2832, flick = 0.85 + 0.15 * Math.sin(st.tick * 0.5);
    for (let k = 0; k < NST; k++) { const th = k / NST * 6.2832; const x = cx + Math.sin(th) * Rx, y = cy - Math.cos(th) * Ry;
      const filled = th <= ob * 6.2832; let d = (head - th) % 6.2832; if (d < 0) d += 6.2832; const tail = d < 1.4 ? 1 - d / 1.4 : 0;
      if (done) put(x, y, k % 5 === 0 ? "*" : ":", green, 235 * flick);
      else if (tail > 0.02) put(x, y, tail > 0.82 ? "*" : (tail > 0.5 ? "+" : "."), tail > 0.5 ? hot : cyan, 120 + 135 * tail);
      else if (filled) put(x, y, ":", gold, 205);
      else put(x, y, ".", base, 85); }
    if (done) { const A = (st.tick % 10) < 7 ? 255 : 70;   // 闪烁 √（背景层笔画）
      for (let t = 0; t <= 1.001; t += 0.05) { put(cx - 5 + 3.4 * t, cy + 0 + 2.2 * t, "\\", green, A); put(cx - 1.6 + 5.2 * t, cy + 2.2 - 5.6 * t, "/", green, A); } }
    else { const c = clamp(140 + 115 * Math.sin(st.tick * 0.3), 60, 255); put(cx, cy, "*", hot, c); }
  }

  // 背景：深蓝字符自上而下急落、带拖尾（画到离屏层，再套毛玻璃模糊）
  function drawRain(g2, st) {
    const fs = Math.max(6, Math.floor(chh * 0.9)); g2.font = `${fs}px ${FONT}`; g2.textAlign = "center"; g2.textBaseline = "alphabetic";
    const cols = 30;
    for (let c = 0; c < cols; c++) {
      const gx = Math.round((c + 0.5) / cols * COLS);
      const speed = 1.1 + bit(c, 3) * 1.6, head = ((st.tick * speed + bit(c, 9) * 400) % (ROWS + 18)) - 9;
      const len = 7 + (bit(c, 5) * 9 | 0);
      for (let k = 0; k < len; k++) { const y = head - k; if (y < 0 || y >= ROWS) continue; const a = 1 - k / len;
        g2.fillStyle = `rgba(${k === 0 ? "120,165,240" : "34,74,165"},${clamp(a * 0.6, 0, 0.65)})`;
        g2.fillText(String.fromCharCode(48 + ((bit(c * 13 + k, (st.tick >> 2)) * 10) | 0)), ox + (gx + 0.5) * cw, oy + (y + 0.82) * chh); }
    }
  }

  function resize(w, h) { W = w; H = h; canvas.width = w; canvas.height = h; bgc.width = w; bgc.height = h; chh = Math.floor((h * 0.99) / ROWS); cw = Math.floor((w * 0.99) / COLS); ox = ((w - cw * COLS) / 2) | 0; oy = ((chh * 0.4)) | 0; }
  function sceneFade() { return 1; }   // 幕界不再淡黑：①→②→②.5→③ 全部靠组件 morph / 噪声收束过渡
  function draw(st, m) { fill(st, m); const _tt = st.tick / pack.fps; const fade = sceneFade(_tt);
    // ③ 入场：introY（fill 设定）= 刷新前沿；整帧闪烁刷新（重整旗鼓）
    const introOn = introY < 1e9; const flick = introOn ? (bit(st.tick, 7) < 0.16 ? 0.35 : 1) * (0.65 + 0.35 * Math.abs(Math.sin(_tt * 26))) : 1;
    ctx.fillStyle = "#04070a"; ctx.fillRect(0, 0, W, H);
    bgx.clearRect(0, 0, W, H); drawSpectrum(bgx, st); if (_tt < bootEnd) drawLoader(bgx, st); else if (_tt >= sceneStart) drawHeart(bgx, st, m, introY); drawRain(bgx, st);
    ctx.save(); ctx.filter = "blur(1.6px)"; ctx.globalAlpha = fade * flick; ctx.drawImage(bgc, 0, 0); ctx.restore(); ctx.filter = "none";
    if (flashRGB) { ctx.fillStyle = `rgba(${flashRGB[0]},${flashRGB[1]},${flashRGB[2]},${flashRGB[3]})`; ctx.fillRect(0, 0, W, H); }   // 全屏闪红（失败）
    const fs = Math.max(6, Math.floor(chh * 0.9)); ctx.font = `${fs}px ${FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
    for (let p = 0; p < N; p++) { if (gCh[p] === 32 || gA[p] < 12) continue; const x = p % COLS, y = (p / COLS) | 0; ctx.fillStyle = `rgba(${gR[p]},${gG[p]},${gB[p]},${Math.min(255, ((gA[p] >> 4) << 4) * fade * flick) / 255})`; ctx.fillText(String.fromCharCode(gCh[p]), ox + (x + 0.5) * cw, oy + (y + 0.82) * chh); }
    if (introOn && introY < ROWS + 2) { ctx.fillStyle = "rgba(150,250,255,0.9)"; ctx.fillRect(0, oy + introY * chh, W, Math.max(2, chh * 0.5)); }   // 刷新扫描线
    if (_tt >= powerEnd) { const bo = seg(_tt, powerEnd, powerEnd + 1.1); ctx.fillStyle = `rgba(2,3,6,${bo})`; ctx.fillRect(0, 0, W, H); }   // 断电：POWER 倒下→黑屏死寂
  }

  return { COLS, ROWS, resize, draw, fill };
}
