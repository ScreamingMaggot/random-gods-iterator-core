// canvas 混合渲染：结构用线框+文字，信息流用发光矢量（连续线，不再受 ASCII 限制）。
// 统一符号语法：地址=黄 数据=青 控制=红 中断=紫 时钟=白；总线=有方向+占用率的管道。
import { clamp } from "./util.js";

const COL = { addr: [245, 217, 10], data: [55, 230, 255], ctrl: [255, 90, 74], irq: [200, 107, 255], clk: [234, 255, 248],
  base: [40, 120, 112], text: [191, 238, 230], dim: [22, 60, 56], hit: [70, 230, 140], miss: [255, 80, 70] };
const P = { FETCH: [.11, .17], DECODE: [.29, .17], EXEC: [.47, .17], MEM: [.64, .17], WB: [.82, .17], BUS: [.47, .40], CACHE: [.64, .60], DRAM: [.85, .60], REG: [.47, .78], IRQ: [.11, .60] };
const FLOWCOL = { addr: COL.addr, data: COL.data, ctrl: COL.ctrl, irq: COL.irq };

export function makeView(canvas, cpu) {
  const ctx = canvas.getContext("2d");
  let W = 0, H = 0, prevRegs = null, missFlash = 0, lastEvN = 0;
  const css = (c, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
  const cx = (n) => P[n][0] * W, cy = (n) => P[n][1] * H;

  function resize(w, h) { W = w; H = h; canvas.width = w; canvas.height = h; }

  function box(x, y, w, h, col, label, glow) {
    ctx.lineWidth = 2; ctx.strokeStyle = css(col, 0.9); ctx.fillStyle = css(COL.dim, 0.5);
    ctx.fillRect(x - w / 2, y - h / 2, w, h); if (glow) { ctx.shadowColor = css(col, 0.8); ctx.shadowBlur = glow; } ctx.strokeRect(x - w / 2, y - h / 2, w, h); ctx.shadowBlur = 0;
    ctx.fillStyle = css(COL.text, 0.95); ctx.font = "bold 13px Consolas,monospace"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(label, x, y - h / 2 + 12);
  }
  function flowDot(x, y, col, r) { ctx.fillStyle = css(col, 0.25); ctx.beginPath(); ctx.arc(x, y, r * 2.2, 0, 6.283); ctx.fill(); ctx.fillStyle = css(col, 1); ctx.beginPath(); ctx.arc(x, y, r, 0, 6.283); ctx.fill(); }
  function seg(ax, ay, bx, by, col, w, a) { ctx.strokeStyle = css(col, a); ctx.lineWidth = w; ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke(); }

  function draw(st, m) {
    ctx.fillStyle = "#04070a"; ctx.fillRect(0, 0, W, H);
    const slow = st.slow > 0;
    if (missFlash > 0) missFlash--;
    // 总线管道（占用率=底色亮度 + 队列点）
    const by = cy("BUS");
    seg(cx("FETCH"), by, cx("WB"), by, COL.base, 10, 0.35 + 0.5 * m.busUtil);
    ctx.fillStyle = css(COL.text, 0.8); ctx.font = "11px Consolas,monospace"; ctx.textAlign = "left";
    ctx.fillText("BUS  util " + (m.busUtil * 100 | 0) + "%  queue " + m.queue, cx("FETCH"), by - 12);
    for (let i = 0; i < m.queue && i < 8; i++) flowDot(cx("WB") - 14 - i * 16, by, COL.data, 3);
    // 流水线 5 级
    const stages = ["FETCH", "DECODE", "EXEC", "MEM", "WB"];
    stages.forEach((s, i) => {
      const ins = st.pipe[i]; const occ = !!ins;
      box(cx(s), cy(s), W * 0.13, H * 0.12, occ ? COL.clk : COL.base, s, occ ? 12 : 0);
      if (ins) { ctx.fillStyle = css(COL.data, 1); ctx.font = "bold 15px Consolas,monospace"; ctx.fillText(ins.op, cx(s), cy(s) + 6); ctx.fillStyle = css(COL.text, 0.5); ctx.font = "10px Consolas,monospace"; ctx.fillText("#" + ins.id, cx(s), cy(s) + 22); }
    });
    // 停顿气泡
    if (st.stall > 0) { ctx.fillStyle = css(COL.miss, 1); ctx.font = "bold 12px Consolas,monospace"; ctx.fillText("STALL", (cx("DECODE") + cx("EXEC")) / 2, cy("EXEC") + H * 0.09); }
    // REG 寄存器堆（内容会变，写回闪烁）
    box(cx("REG"), cy("REG"), W * 0.30, H * 0.16, COL.base, "REGISTERS  EAX..ESP");
    st.regs.forEach((v, i) => {
      const rx = cx("REG") - W * 0.13 + (i % 4) * (W * 0.065), ry = cy("REG") - H * 0.03 + ((i / 4) | 0) * (H * 0.05);
      const changed = prevRegs && prevRegs[i] !== v;
      ctx.fillStyle = css(changed ? COL.data : COL.base, changed ? 1 : 0.6); ctx.fillRect(rx, ry, W * 0.055, H * 0.036);
      ctx.fillStyle = css(changed ? [0, 20, 24] : COL.text, 1); ctx.font = "11px Consolas,monospace"; ctx.textAlign = "center"; ctx.fillText(v.toString(16).toUpperCase().padStart(4, "0"), rx + W * 0.0275, ry + H * 0.018);
    });
    // 标志位
    const fl = ["Z", "C", "S", "O"]; fl.forEach((k, i) => { ctx.fillStyle = css(st.flags[k] ? COL.clk : COL.base, 0.9); ctx.font = "12px Consolas,monospace"; ctx.textAlign = "left"; ctx.fillText(k + "=" + st.flags[k], cx("REG") - W * 0.13 + i * (W * 0.06), cy("REG") + H * 0.075); });
    // CACHE 组相联（命中绿/缺失红闪）
    box(cx("CACHE"), cy("CACHE"), W * 0.16, H * 0.16, missFlash > 0 ? COL.miss : COL.base, "CACHE 4x4  hit " + (m.hitRate * 100 | 0) + "%", missFlash > 0 ? 14 : 0);
    st.cache.forEach((c, i) => { const cxx = cx("CACHE") - W * 0.065 + (i % 4) * (W * 0.033), cyy = cy("CACHE") - H * 0.04 + ((i / 4) | 0) * (H * 0.028); ctx.fillStyle = css(c.valid ? (missFlash > 0 && i % 4 === 0 ? COL.miss : COL.hit) : COL.dim, 0.9); ctx.fillRect(cxx, cyy, W * 0.026, H * 0.02); });
    // DRAM
    box(cx("DRAM"), cy("DRAM"), W * 0.12, H * 0.12, COL.base, "DRAM / IO");
    // ALU 进位链（占用热力）
    const aluX = cx("EXEC"), aluY = cy("EXEC") + H * 0.06;
    for (let i = 0; i < 8; i++) { const on = rngBit(st.tick, i) < m.alu; ctx.fillStyle = css(on ? [255, 180 - 120 * i / 8, 40] : COL.dim, 0.9); ctx.fillRect(aluX - 60 + i * 15, aluY, 11, 8); }
    // IRQ 队列 + 仲裁器 + 栈
    box(cx("IRQ"), cy("IRQ"), W * 0.16, H * 0.20, st.irqActive ? COL.irq : COL.base, "INTERRUPTS", st.irqActive ? 12 : 0);
    st.irqPend.slice(0, 4).forEach((q, i) => { ctx.fillStyle = css(COL.irq, 0.9); ctx.font = "11px Consolas,monospace"; ctx.textAlign = "left"; ctx.fillText(q.n + " p" + q.p, cx("IRQ") - W * 0.07, cy("IRQ") - H * 0.05 + i * 14); });
    if (st.irqActive) { ctx.fillStyle = css(COL.irq, 1); ctx.font = "bold 12px Consolas,monospace"; ctx.textAlign = "center"; ctx.fillText("◄ " + st.irqActive.n + " ISR", cx("IRQ"), cy("IRQ") + H * 0.06); }
    ctx.fillStyle = css(COL.clk, 0.8); ctx.font = "11px Consolas,monospace"; ctx.textAlign = "left"; ctx.fillText("STACK depth " + st.stack.length, cx("IRQ") - W * 0.07, cy("IRQ") + H * 0.085);
    // 信息流（发光包沿路径跑 + 拖尾）
    for (const fl of st.flows) { const col = FLOWCOL[fl.kind]; const pts = fl.path.map((n) => [cx(n), n === "BUS" ? by : cy(n)]); const u = fl.age / fl.ttl; const pos = alongPoly(pts, u);
      const ptail = alongPoly(pts, Math.max(0, u - 0.12)); seg(ptail[0], ptail[1], pos[0], pos[1], col, 3, 0.5); flowDot(pos[0], pos[1], col, 4); }
    // 逻辑分析仪波形轨
    drawWave(st, m);
    // 事件字幕（最近）
    const recent = st.events.slice(-3); ctx.textAlign = "left"; ctx.font = "12px Consolas,monospace";
    recent.forEach((e, i) => { ctx.fillStyle = css(e.col === "#ff4a4a" ? COL.miss : e.col === "#c86bff" ? COL.irq : COL.text, 0.9); ctx.fillText("· " + e.s, 16, H - 96 + i * 15); });
    // HUD 顶
    ctx.textAlign = "left"; ctx.fillStyle = css(COL.text, 1); ctx.font = "bold 14px Consolas,monospace";
    ctx.fillText("RANDOM GODS · ITERATOR CORE — OUT-OF-ORDER BIOCPU", 16, 22);
    ctx.font = "12px Consolas,monospace"; ctx.fillStyle = css(COL.data, 1);
    ctx.fillText("LOAD " + (m.load * 100 | 0) + "%  INFLIGHT " + m.inflight + "  BUS " + (m.busUtil * 100 | 0) + "%  ALU " + (m.alu * 100 | 0) + "%  HIT " + (m.hitRate * 100 | 0) + "%  RET " + m.retired, 16, 40);
    ctx.fillStyle = css(COL.irq, 1); ctx.fillText("ENTROPY " + (m.entropy * 100 | 0) + "%", W - 150, 40);
    if (slow) { ctx.fillStyle = css(COL.miss, 1); ctx.font = "bold 16px Consolas,monospace"; ctx.fillText("◉ SLOW-MO  ·  critical event", W - 300, 22); }
    prevRegs = st.regs.slice();
    if (st.events.length > lastEvN) { const ne = st.events[st.events.length - 1]; if (ne && /MISS/.test(ne.s)) missFlash = 6; lastEvN = st.events.length; }
  }

  function alongPoly(pts, u) { if (pts.length < 2) return pts[0] || [0, 0]; const segs = []; let tot = 0; for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); segs.push(d); tot += d; } let target = clamp(u, 0, 1) * tot; for (let i = 0; i < segs.length; i++) { if (target <= segs[i]) { const a = pts[i], b = pts[i + 1], t = segs[i] ? target / segs[i] : 0; return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]; } target -= segs[i]; } return pts[pts.length - 1]; }
  function rngBit(t, i) { let x = (t * 2654435761 ^ i * 40503) >>> 0; x = Math.imul(x ^ (x >>> 15), 2246822519); return ((x >>> 13) & 1023) / 1023; }

  function drawWave(st, m) {
    const lanes = [["CLK", []], ["BUS", st.busHist.slice()], ["IRQ", []], ["PIPE", []]];
    const y0 = H - 60, lh = 13, x0 = 16, wpx = W - 32;
    ctx.strokeStyle = css(COL.base, 0.4); ctx.lineWidth = 1; ctx.strokeRect(x0, y0 - 4, wpx, lh * 4 + 8);
    const n = 60;
    lanes.forEach((ln, li) => { const col = [COL.clk, COL.data, COL.irq, COL.addr][li]; const yy = y0 + li * lh;
      ctx.fillStyle = css(COL.text, 0.7); ctx.font = "9px Consolas,monospace"; ctx.textAlign = "left"; ctx.fillText(ln[0], x0 + 2, yy + 9);
      ctx.strokeStyle = css(col, 0.9); ctx.lineWidth = 1.5; ctx.beginPath();
      for (let i = 0; i < n; i++) { const x = x0 + 40 + i * (wpx - 44) / n; let v;
        if (li === 0) v = ((st.tick + i) % 4 < 2) ? 1 : 0; // clock
        else if (li === 1) v = st.busHist[st.busHist.length - n + i] || 0; // bus
        else if (li === 2) v = (st.irqActive && i > n - 12) ? 1 : (rngBit(st.tick, i + 99) < 0.06 ? 1 : 0); // irq
        else v = clamp(m.inflight / 5, 0, 1) > 0.5 + 0.4 * Math.sin(i) ? 1 : 0; // pipe occupancy
        const y = yy + (v ? 2 : lh - 2); i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      } ctx.stroke(); });
  }

  return { resize, draw };
}
