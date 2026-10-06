// 全新 CPU 版图（不铺真实 70 间，按功能重排；数据左→右，能量沿顶脊下发）。
// 归一化坐标 rect=[x0,y0,x1,y1]，x右y下 0–1，铺进 COLS×ROWS 字符网格。DOM 无关。
import { hash32 } from "./util.js";

const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

// 域键：FE前端 / EX执行(标量) / MAT矩阵(主计算) / MEM存储 / REG后端退休。NOIC 跨域。
export const FLOORPLAN = [
  { id: "PSU",  name: "能量源",     x0: .020, y0: .015, x1: .170, y1: .100, dom: null },
  { id: "CLKD", name: "时钟分发",   x0: .190, y0: .015, x1: .975, y1: .100, dom: "CLKD" },

  { id: "INT",  name: "中断·外接",  x0: .020, y0: .130, x1: .100, y1: .300, dom: null },
  { id: "BPB",  name: "分支预测",   x0: .120, y0: .130, x1: .250, y1: .300, dom: "FE" },
  { id: "FETCH",name: "取指",       x0: .270, y0: .130, x1: .400, y1: .300, dom: "FE" },
  { id: "DECODE",name:"译码·µ码",   x0: .420, y0: .130, x1: .600, y1: .300, dom: "FE" },
  { id: "ROB",  name: "重命名·ROB", x0: .620, y0: .130, x1: .975, y1: .300, dom: "FE" },

  { id: "ALU",  name: "标量运算×k", x0: .120, y0: .330, x1: .340, y1: .600, dom: "EX" },
  { id: "MAT",  name: "矩阵运算器", x0: .380, y0: .320, x1: .975, y1: .880, dom: "MAT" },

  { id: "REG",  name: "寄存器堆",   x0: .020, y0: .350, x1: .100, y1: .850, dom: "REG" },

  { id: "LDST", name: "访存",       x0: .120, y0: .630, x1: .210, y1: .850, dom: "MEM" },
  { id: "L1D",  name: "L1 缓存",    x0: .220, y0: .630, x1: .300, y1: .850, dom: "MEM" },
  { id: "L23",  name: "L2/L3 缓存", x0: .120, y0: .880, x1: .430, y1: .965, dom: "MEM" },
  { id: "DRAM", name: "DRAM·总线",  x0: .450, y0: .880, x1: .720, y1: .965, dom: "MEM" },
  { id: "WB",   name: "退休",       x0: .760, y0: .880, x1: .975, y1: .965, dom: "REG" },
];

// 功能体之间的数据流（信息包/柔性导管走这些真实弧）
export const DATAFLOW = [
  ["FETCH", "DECODE"], ["DECODE", "ROB"], ["ROB", "ALU"], ["ROB", "MAT"],
  ["ALU", "REG"], ["MAT", "REG"], ["LDST", "L1D"], ["L1D", "L23"], ["L23", "DRAM"],
  ["DRAM", "LDST"], ["REG", "WB"], ["BPB", "FETCH"], ["INT", "DECODE"], ["DECODE", "BPB"],
];

// 终极问题常量（矩阵运算器反复求解的那张；16 进制整数矩阵，8×10）
export const QUESTION = [
  [0x1F, 0x7A, 0x3C, 0x02, 0x9D, 0x4B, 0xE6, 0x11, 0x58, 0xC0],
  [0x2B, 0x6E, 0x07, 0xA3, 0x1C, 0xF5, 0x90, 0x3D, 0x82, 0x64],
  [0x77, 0x0D, 0xB1, 0x48, 0x20, 0xCE, 0x59, 0xA6, 0x03, 0x9F],
  [0x50, 0xC8, 0x1A, 0xE7, 0x6B, 0x02, 0xF9, 0x34, 0x7D, 0x21],
  [0xA2, 0x15, 0x6F, 0x0C, 0x3E, 0xB8, 0x47, 0xD0, 0x5A, 0x93],
  [0x39, 0xE0, 0x54, 0x2C, 0x1B, 0x76, 0x0A, 0xC5, 0x88, 0xF1],
  [0xC4, 0x23, 0x8B, 0x90, 0xE1, 0x05, 0x7D, 0x6A, 0x1F, 0x42],
  [0x0E, 0x97, 0x2A, 0x5D, 0x83, 0xC6, 0x30, 0xB2, 0xEE, 0x71],
];

export function buildLayout(pack) {
  const g = pack.engine.glyph_grid || [95, 55];
  const COLS = g[0], ROWS = g[1];
  const cellDom = new Int8Array(COLS * ROWS).fill(-1);   // 域索引（见 sim.DOMS 顺序）
  const cellRoom = new Int16Array(COLS * ROWS).fill(-1); // 版图块索引
  const cellKind = new Uint8Array(COLS * ROWS);          // 0 空 1 导管 2 块边 3 块内 4 标题

  const blocks = FLOORPLAN.map((b) => {
    const c0 = clamp(Math.round(b.x0 * COLS), 0, COLS - 1), c1 = clamp(Math.round(b.x1 * COLS), 0, COLS - 1);
    const r0 = clamp(Math.round(b.y0 * ROWS), 0, ROWS - 1), r1 = clamp(Math.round(b.y1 * ROWS), 0, ROWS - 1);
    return { ...b, c0, c1, r0, r1, cx: (c0 + c1) >> 1, cy: (r0 + r1) >> 1, w: c1 - c0 + 1, h: r1 - r0 + 1 };
  });
  const byId = new Map(blocks.map((b) => [b.id, b]));
  const domOrder = ["CLKD", "FE", "EX", "MAT", "MEM", "REG"];

  blocks.forEach((b, bi) => {
    for (let y = b.r0; y <= b.r1; y++) for (let x = b.c0; x <= b.c1; x++) {
      const edge = x === b.c0 || x === b.c1 || y === b.r0 || y === b.r1;
      const p = y * COLS + x;
      if (cellKind[p] === 3) continue;                    // 已被更大块占据（极少重叠）
      cellRoom[p] = bi;
      cellKind[p] = edge ? 2 : (y === b.r0 + 1 ? 4 : 3);
      const di = domOrder.indexOf(b.dom); if (di >= 0) cellDom[p] = di;
    }
    b.ix0 = b.c0 + 1; b.ix1 = b.c1 - 1; b.iy0 = b.r0 + 2; b.iy1 = b.r1 - 1; // 内部格（标题行下方）
  });

  // MAT 阵列坐标（systolic，水平居中于块内，标题行下方）
  const MAT = byId.get("MAT");
  const ARR = Math.max(6, Math.min(MAT.w - 4, MAT.h - 5, 16));
  const arr = { c0: MAT.c0 + 2 + Math.floor((MAT.w - 4 - ARR) / 2), r0: MAT.r0 + 3, n: ARR };

  return { COLS, ROWS, cellDom, cellRoom, cellKind, blocks, byId, domOrder, arr,
    dataflow: DATAFLOW, Q: QUESTION, qn: [QUESTION.length, QUESTION[0].length] };
}
