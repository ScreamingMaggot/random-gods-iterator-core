// 离线逐帧校核：sim 是 f 的纯函数，直接在 node 跑，判定由代码按阈值自动给（不靠眼睛）。
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { decodePack } from "./src/pack.js";
import { createSim } from "./src/sim.js";

const here = dirname(fileURLToPath(import.meta.url));
const pack = decodePack(JSON.parse(readFileSync(resolve(here, "../out/pack.json"), "utf8")));
const sim = createSim(pack);
const { COLS, ROWS, N } = sim;
const F = (t) => Math.round(t * pack.fps);
let fail = 0; const bad = (m) => { console.log("  FAIL " + m); fail++; };

function run(t) { const st = sim.stateAt(F(t)); return { st, s: sim.snapshot(st) }; }
function nanCheck(t) {
  const { st } = run(t);
  for (let p = 0; p < N; p++) {
    if ([sim.gR[p], sim.gG[p], sim.gB[p], sim.gA[p]].some((v) => Number.isNaN(v))) return `NaN@${p}`;
    if (sim.gCh[p] < 9 || sim.gCh[p] > 126) return `非打印码 ${sim.gCh[p]}@${p}`;
  }
  return null;
}

console.log("== 逐帧关键状态 ==");
for (const t of [0.5, 3, 8, 25, 40, 70, 100, 118, 125, 140, 150, 166, 186, 190, 193, 195, 198]) {
  const { st, s } = run(t);
  const ph = sim.DOMS.map((d) => `${d.key}${st.S[d.key].ph.toFixed(1)}`).join(" ");
  console.log(`t=${String(t).padStart(5)} ${st.role.padEnd(8)} 亮${String(s.bright).padStart(4)} 非空${String(s.non).padStart(4)} 红${String(s.red).padStart(3)} 彩${String(s.chroma).padStart(3)} 熵${(st.ent*100|0)} 亚稳${(st.glitch*100|0)} 电${(st.power*100|0)}%  ${ph}`);
  const err = nanCheck(t); if (err) bad(`t=${t} ${err}`);
}

console.log("\n== 断言 ==");
// 1. 确定性：同 f 两次逐格相同
sim.stateAt(F(125)); const a = Uint8Array.from(sim.gCh); const aa = [Uint8Array.from(sim.gR), Uint8Array.from(sim.gG), Uint8Array.from(sim.gA)];
sim.stateAt(F(125)); const b = Uint8Array.from(sim.gCh); const bb = [Uint8Array.from(sim.gR), Uint8Array.from(sim.gG), Uint8Array.from(sim.gA)];
if (a.join() !== b.join() || aa.some((x, i) => x.join() !== bb[i].join())) bad("非确定性：同帧两次输出不同"); else console.log("OK 确定性");

// 2. 稳态有内容（用非空格计数，亮度受幕情绪影响不作硬门）
if (run(40).s.non < 800) bad("稳态帧内容太少(<800 非空格)"); else console.log("OK 稳态内容");

// 3. 熵高潮红/乱更多
const calm = run(40).s, peak = run(125).s, gl = run(140).s;
if (!(peak.red + gl.red) > calm.red) bad("熵峰未比平静帧更多红/亚稳"); else console.log("OK 熵峰亚稳增强");

// 4. 断电：内容量单调熄灭到近零（尾声光标另测）
const n125 = run(125).s.non, n186 = run(186).s.non, n190 = run(190).s.non, n198 = run(198).s.non;
const b125 = run(125).s.bright, b193 = run(193).s.bright;
if (!(b193 <= b125 && n186 < n125 && n190 <= n186 && n190 <= 40)) bad(`断电非单调 非空 ${n125}->${n186}->${n190} 亮 ${b125}->${b193}`); else console.log("OK 断电单调熄灭");
if (n198 > 40) bad(`silence 尾声未近全黑(非空=${n198})`); else console.log("OK 尾声留白(光标)");

// 5. 全帧扫一遍无异常
let thrown = "";
try { for (let f = 0; f < pack.T; f += 5) sim.stateAt(f); } catch (e) { thrown = e.message; }
if (thrown) bad("全帧扫描抛错: " + thrown); else console.log("OK 全帧无异常");

console.log("\n结论: " + (fail === 0 ? "全部通过" : fail + " 项未过"));
process.exit(fail === 0 ? 0 : 1);
