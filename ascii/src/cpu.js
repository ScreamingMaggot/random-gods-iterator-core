// 事件驱动的 CPU 微架构仿真（无 DOM）。确定性：simToFrame(f) 从 0 tick 到 f 可 seek。
// 目标：让"多股信息流在有限资源上并行/排队/抢占/写回/改变状态"真的发生——
// 每个运动都代表信息方向或状态变化。音乐能量=负载：越响→发射越多、竞争越凶、队列越长、ALU越热。
import { mulberry32, clamp } from "./util.js";

const OPS = ["ADD", "SUB", "AND", "OR", "SHL", "MUL", "MOV", "LOAD", "STORE", "CMP", "JMP", "BEQ"];
const IRQ_SRC = [{ n: "TIMER", p: 3 }, { n: "DISK", p: 5 }, { n: "NET", p: 7 }, { n: "KBD", p: 2 }];
const NODES = ["FETCH", "DECODE", "EXEC", "MEM", "WB", "REG", "CACHE", "DRAM", "BUS", "IRQ"];

export function createCPU(pack) {
  const T = pack.T, fps = pack.fps;
  const raw = (n, f) => (pack.ch[n] ? pack.ch[n][clamp(f | 0, 0, T - 1)] / 255 : 0);
  let rng, st;

  function reset() {
    rng = mulberry32(0x5eed);
    st = {
      tick: 0, pc: 0x4000, pipe: [null, null, null, null, null], stall: 0,
      regs: Array.from({ length: 8 }, (_, i) => (0x1000 + i * 0x1111) & 0xffff), rnames: ["EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP", "ESP"],
      flags: { Z: 0, C: 0, S: 0, O: 0 }, stack: [],
      cache: Array.from({ length: 16 }, () => ({ valid: false, tag: -1, dirty: 0, mesi: "I" })), sets: 4, ways: 4, lru: [0, 1, 2, 3].map(() => [0, 1, 2, 3]),
      cop: null,                                   // 当前 cache 访问序列 {phase,t,index,tag,offset,way,miss,wr}
      dram: { cmd: "IDLE", t: 0, bank: 0, row: -1, refT: 120, banks: [0, 0, 0, 0] },
      busQ: [], busBusy: 0, busHist: [], dma: null, dmaTimer: 0,
      irqPend: [], irqActive: null, isrLeft: 0,
      flows: [], events: [], slow: 0,
      hits: 0, misses: 0, issued: 0, retired: 0, aluHeat: 0,
      load: 0, entropy: 0, power: 1,
    };
  }
  reset();

  const pushFlow = (kind, path) => { if (st.flows.length < 60) st.flows.push({ kind, path, age: 0, ttl: 7 }); };
  const ev = (s, col) => { if (st.events.length < 80) st.events.push({ t: st.tick, s, col }); };

  function makeInstr() {
    const op = OPS[(rng() * OPS.length) | 0];
    const rd = (rng() * 8) | 0, rs = (rng() * 8) | 0;
    const addr = (0x1000 + ((rng() * 0x800) | 0)) & 0xffff;
    return { op, rd, rs, addr, id: st.issued, cyc: 0 };
  }

  function cacheAccess(addr) {
    const set = (addr >> 4) % st.sets, tag = addr >> 8;
    const base = set * st.ways;
    for (let w = 0; w < st.ways; w++) if (st.cache[base + w].valid && st.cache[base + w].tag === tag) {
      st.lru[set] = [w, ...st.lru[set].filter((x) => x !== w)]; st.hits++; return { hit: true, set, way: w };
    }
    const way = st.lru[set][st.ways - 1]; st.cache[base + way] = { valid: true, tag };
    st.lru[set] = [way, ...st.lru[set].slice(0, st.ways - 1)]; st.misses++;
    return { hit: false, set, way };
  }

  const DUR = [2, 2, 2, 1, 3, 3, 1];
  function decideHit(c) { const base = c.index * st.ways; c.way = -1; for (let w = 0; w < st.ways; w++) if (st.cache[base + w].valid && st.cache[base + w].tag === c.tag) { c.way = w; break; } c.miss = c.way < 0; }
  function onHit(c) { const base = c.index * st.ways; const L = st.cache[base + c.way]; st.lru[c.index] = [c.way, ...st.lru[c.index].filter((x) => x !== c.way)]; if (c.wr) { L.dirty = 1; L.mesi = "M"; } pushFlow("data", ["CACHE", "MEM"]); st.busBusy = Math.max(st.busBusy, 1); }
  function pickVictim(c) { const base = c.index * st.ways; c.victim = st.lru[c.index][st.ways - 1]; c.vd = st.cache[base + c.victim]; }
  function refill(c) { const base = c.index * st.ways; const L = st.cache[base + c.victim]; L.valid = true; L.tag = c.tag; L.dirty = c.wr ? 1 : 0; L.mesi = c.wr ? "M" : "E"; st.lru[c.index] = [c.victim, ...st.lru[c.index].filter((x) => x !== c.victim)]; }
  function triggerDram(cmd) { st.dram.cmd = cmd; st.dram.t = 0; if (cmd === "ACT") st.dram.row = st.cop ? st.cop.tag & 0xff : 0; }
  function advanceCop() { const c = st.cop; if (!c) return;
    if (c.t === 0) {
      if (c.phase === 1) decideHit(c);
      else if (c.phase === 2) { if (c.miss) { st.misses++; ev("CACHE MISS 0x" + c.addr.toString(16), "#ff4a4a"); st.slow = 5; pickVictim(c); pushFlow("ctrl", ["CACHE", "DRAM"]); } else { st.hits++; onHit(c); } }
      else if (c.phase === 4) { if (c.vd && c.vd.dirty) { triggerDram("WR"); ev("write-back dirty → DRAM", "#ff9a3c"); } }
      else if (c.phase === 5) { triggerDram("ACT"); refill(c); pushFlow("data", ["DRAM", "BUS", "CACHE"]); }
    }
    c.t++;
    if (c.t >= DUR[c.phase]) { c.t = 0; c.phase = (c.phase === 2 && !c.miss) ? 6 : c.phase + 1; if (c.phase >= 7) st.cop = null; }
  }
  function advanceDram() { const d = st.dram; d.t++; d.refT--; if (d.refT <= 0 && d.cmd === "IDLE") { d.cmd = "REF"; d.t = 0; d.refT = 120; }
    const dur = { ACT: 3, RD: 3, WR: 3, PRE: 2, REF: 6, IDLE: 1 }[d.cmd] || 2;
    if (d.cmd === "ACT" && d.t === 1) d.row = (d.row + 7) & 0xff;
    if (d.cmd === "RD" && d.t === 1) pushFlow("data", ["DRAM", "BUS", "CACHE"]);
    if (d.t >= dur) { if (d.cmd === "ACT") { d.cmd = "RD"; d.t = 0; } else if (d.cmd === "RD" || d.cmd === "WR") { d.cmd = "PRE"; d.t = 0; } else { d.cmd = "IDLE"; d.t = 0; d.row = -1; } }
  }

  function tick(f) {
    f = clamp(f | 0, 0, T - 1);
    const energy = clamp(raw("rms", f) * 0.5 + raw("onset", f) * 0.6 + raw("bass_on", f) * 0.35, 0, 1);
    const tension = raw("tension", f);
    st.load = clamp(0.25 + 0.75 * energy, 0, 1) * clamp(pack.electricF(f), 0, 1);
    st.entropy = clamp((raw("flat", f) - 0.0) / 0.2, 0, 1);
    st.power = pack.electricF(f);
    st.tick++;
    st.beat = raw("onset", f) > 0.5;                       // 音触发：驱动一次放电交互
    st.beatPhase = raw("pulse", f);
    if (st.slow > 0) st.slow--;

    // —— 取指：能量越高发射越密（并发）——
    if (!st.pipe[0] && st.stall === 0 && rng() < 0.35 + 0.6 * st.load) { st.pipe[0] = makeInstr(); st.issued++; pushFlow("addr", ["FETCH", "BUS", "CACHE"]); }

    // —— Cache/DRAM 微序列：MEM 级 LOAD/STORE 触发多周期访问（缺失停顿流水线=竞争）——
    if (!st.cop && st.pipe[3] && (st.pipe[3].op === "LOAD" || st.pipe[3].op === "STORE")) {
      const a = st.pipe[3].addr;
      st.cop = { phase: 0, t: 0, index: (a >> 4) % st.sets, tag: a >> 8, offset: a & 0xf, way: -1, miss: false, wr: st.pipe[3].op === "STORE", addr: a };
      pushFlow("addr", ["MEM", "BUS", "CACHE"]);
    }
    if (st.cop) advanceCop();
    advanceDram();
    const copHold = !!st.cop;

    // —— 流水推进（从后往前），停顿或 cache 占用则冻结前端 ——
    const busy = st.busBusy > 0 || st.busQ.length > 2;
    if (st.stall > 0) st.stall--;
    if (st.stall === 0 && !copHold) {
      for (let i = 4; i >= 1; i--) {
        const ins = st.pipe[i - 1]; if (!ins) continue;
        if (i === 3 && (ins.op === "LOAD" || ins.op === "STORE")) { st.pipe[i] = ins; st.pipe[i - 1] = null; }
        else { st.pipe[i] = ins; st.pipe[i - 1] = null; }
      }
      // EX：ALU 占用 + 进位链闪
      if (st.pipe[2]) { st.aluHeat = clamp(st.aluHeat + 0.3, 0, 1); pushFlow("ctrl", ["DECODE", "EXEC"]); }
      // WB：写回寄存器 + 标志翻转（状态变化）
      const wb = st.pipe[4];
      if (wb) {
        const a = st.regs[wb.rs], b = (wb.addr & 0xff);
        let res = (a + b) & 0xffff;
        if (wb.op === "SUB") res = (a - b) & 0xffff; if (wb.op === "AND") res = a & b; if (wb.op === "MUL") res = (a * (b | 1)) & 0xffff;
        if (wb.op !== "LOAD" && wb.op !== "STORE" && wb.op !== "JMP") { st.regs[wb.rd] = res; pushFlow("data", ["EXEC", "REG"]); }
        st.flags.Z = res === 0 ? 1 : 0; st.flags.C = res > 0xffff ? 1 : 0; st.flags.S = (res >> 15) & 1;
        st.retired++; st.pipe[4] = null;
      }
      // 分支误判：冲刷流水 + PC 跳变（状态剧变 + 慢动作）
      const ex = st.pipe[2];
      if (ex && (ex.op === "JMP" || ex.op === "BEQ") && rng() < 0.08 + 0.35 * tension) {
        st.pipe[1] = st.pipe[2] = st.pipe[3] = null; st.pc = (st.pc + 0x40 + ((rng() * 0x200) | 0)) & 0xffff;
        st.slow = 8; ev("BRANCH MISPREDICT → flush", "#ff4a4a"); pushFlow("ctrl", ["EXEC", "FETCH"]);
      } else if (ex) { st.pc = (st.pc + 4) & 0xffff; }
    } else {
      // 气泡：停顿周期前端冻结、后段继续排空
      st.pipe[0] = null;
    }

    // —— 总线服务队列（仲裁 + 占用率）——
    if (st.busBusy > 0) st.busBusy--;
    else if (st.busQ.length) { const j = st.busQ[0]; j.left--; if (j.left <= 0) { st.busQ.shift(); if (j.kind === "dma") ev("DMA xfer done", "#c86bff"); } }
    st.busHist.push(busy ? 1 : 0); if (st.busHist.length > 40) st.busHist.shift();

    // —— DMA 抢总线（竞争）——
    st.dmaTimer--; if (st.dmaTimer <= 0 && rng() < 0.5 + 0.5 * st.load) { st.dmaTimer = 20 + ((rng() * 40) | 0); st.busQ.push({ kind: "dma", left: 3 }); pushFlow("data", ["DRAM", "BUS"]); ev("DMA request bus", "#c86bff"); }

    // —— 中断：多源排队 + 仲裁器选最高优先级 + 抢占压栈 + 返回恢复 ——
    for (const s of IRQ_SRC) if (rng() < 0.01 + 0.05 * st.load * (s.p / 7)) if (!st.irqPend.find((x) => x.n === s.n)) { st.irqPend.push({ ...s }); pushFlow("irq", ["IRQ", "BUS"]); }
    if (!st.irqActive && st.irqPend.length && st.pipe[1]) {
      st.irqPend.sort((a, b) => b.p - a.p); const win = st.irqPend.shift();
      st.stack.push(st.pc); st.irqActive = win; st.isrLeft = 6 + ((rng() * 8) | 0); st.pc = 0x8000 + win.p * 0x10;
      st.pipe[1] = null; st.slow = 10; ev("IRQ " + win.n + " preempt (prio " + win.p + ")", "#c86bff"); pushFlow("irq", ["IRQ", "DECODE"]);
    } else if (st.irqActive) { st.isrLeft--; if (st.isrLeft <= 0) { st.pc = st.stack.pop() || st.pc; ev("IRET → " + st.irqActive.n, "#c86bff"); st.irqActive = null; pushFlow("ctrl", ["EXEC", "FETCH"]); } }

    st.aluHeat = clamp(st.aluHeat * 0.82, 0, 1);
    // flows 老化
    for (const fl of st.flows) fl.age++; st.flows = st.flows.filter((fl) => fl.age < fl.ttl);
    return st;
  }

  function metrics() {
    const inflight = st.pipe.filter(Boolean).length;
    const hitRate = st.hits + st.misses ? st.hits / (st.hits + st.misses) : 1;
    const busUtil = st.busHist.reduce((a, b) => a + b, 0) / Math.max(1, st.busHist.length);
    return { inflight, hitRate, busUtil, queue: st.busQ.length + st.irqPend.length, issued: st.issued, retired: st.retired, alu: st.aluHeat, load: st.load, entropy: st.entropy, power: st.power, beat: !!st.beat };
  }
  function simToFrame(f) { reset(); for (let k = 0; k <= f; k++) tick(k); return st; }

  return { reset, tick, simToFrame, metrics, NODES, OPS, get state() { return st; } };
}
