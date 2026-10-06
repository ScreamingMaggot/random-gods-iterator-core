// 离线校核 CPU 事件仿真：确定性、并发、竞争事件、吞吐随时间增长、无 NaN。
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { decodePack } from "./src/pack.js";
import { createCPU } from "./src/cpu.js";

const here = dirname(fileURLToPath(import.meta.url));
const pack = decodePack(JSON.parse(readFileSync(resolve(here, "../out/pack.json"), "utf8")));
const cpu = createCPU(pack);
let fail = 0; const bad = (m) => { console.log("  FAIL " + m); fail++; };
const F = (t) => Math.round(t * pack.fps);

console.log("== 逐时刻指标 ==");
for (const t of [2, 10, 30, 60, 90, 120, 135, 160, 186, 196]) {
  const st = cpu.simToFrame(F(t)); const m = cpu.metrics();
  const evs = st.events.map((e) => e.s.split(" ")[0]).join(",");
  console.log(`t=${String(t).padStart(4)} 发射${String(m.issued).padStart(4)} 退休${String(m.retired).padStart(4)} 在飞${m.inflight} 总线${(m.busUtil * 100 | 0)}% ALU${(m.alu * 100 | 0)}% 命中${(m.hitRate * 100 | 0)}% 队列${m.queue} 负载${(m.load * 100 | 0)}% 事件[${evs.slice(0, 40)}]`);
  const nums = [m.inflight, m.busUtil, m.hitRate, m.alu, m.load, m.queue];
  if (nums.some((v) => Number.isNaN(v) || !isFinite(v))) bad(`t=${t} 指标 NaN/Inf`);
  if (!(m.busUtil >= 0 && m.busUtil <= 1 && m.hitRate >= 0 && m.hitRate <= 1)) bad(`t=${t} 比率越界`);
}

console.log("\n== 断言 ==");
// 确定性
const a = JSON.stringify(cpu.simToFrame(F(120)).pipe) + cpu.metrics().retired;
const b = JSON.stringify(cpu.simToFrame(F(120)).pipe) + cpu.metrics().retired;
if (a !== b) bad("非确定性：同帧两次不同"); else console.log("OK 确定性");

// 吞吐随时间增长（退休单调）
const r10 = cpu.simToFrame(F(10)) && cpu.metrics().retired, r120 = (cpu.simToFrame(F(120)), cpu.metrics().retired);
if (!(r120 > r10)) bad(`退休未增长 ${r10}->${r120}`); else console.log("OK 退休递增 " + r10 + "->" + r120);

// 并发：某帧在飞 >1
let maxInflight = 0; for (let f = 0; f < pack.T; f += 7) { cpu.simToFrame(f); maxInflight = Math.max(maxInflight, cpu.metrics().inflight); }
if (!(maxInflight >= 2)) bad("从未并发(在飞<2)"); else console.log("OK 并发 最大在飞=" + maxInflight);

// 竞争事件真的发生：CACHE MISS / IRQ / MISPREDICT 至少各一次
cpu.simToFrame(pack.T - 1); const allEv = cpu.state.events.length;
cpu.simToFrame(F(150)); let miss = 0, irq = 0, mis = 0;
for (let f = 0; f < pack.T; f += 3) { const s = cpu.simToFrame(f); for (const e of s.events) { if (/MISS/.test(e.s)) miss++; if (/IRQ/.test(e.s)) irq++; if (/MISPRED/.test(e.s)) mis++; } }
if (!(miss > 0 && irq > 0 && mis > 0)) bad(`竞争事件不足 miss${miss} irq${irq} mis${mis}`); else console.log(`OK 竞争/状态事件 miss${miss} irq${irq} mis${mis}`);

// 全帧无异常
let thrown = ""; try { for (let f = 0; f < pack.T; f += 5) cpu.simToFrame(f); } catch (e) { thrown = e.message; }
if (thrown) bad("全帧抛错: " + thrown); else console.log("OK 全帧无异常");

console.log("\n结论: " + (fail === 0 ? "全部通过" : fail + " 项未过"));
process.exit(fail === 0 ? 0 : 1);
