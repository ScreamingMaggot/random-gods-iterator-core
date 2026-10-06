// 通用小工具：确定性哈希/PRNG 与颜色叠加。全片"每帧纯函数于 f"依赖这里的确定性哈希。
export const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

export function hash32(x) {
  x = x >>> 0;
  x = Math.imul(x ^ (x >>> 16), 0x45d9f3b);
  x = Math.imul(x ^ (x >>> 16), 0x45d9f3b);
  x ^= x >>> 16;
  return x >>> 0;
}

export const rnd = (a, b, s) => (hash32(Math.imul(a, 2654435761) ^ Math.imul(b, 40503) ^ Math.imul(s, 2246822519)) % 100000) / 100000;
export const rnd1 = (a, b, s) => hash32(Math.imul(a, 2654435761) ^ Math.imul(b, 40503) ^ Math.imul(s, 2246822519)) / 4294967296;

// 加性混色：把 (r,g,b)*w 累加到累加器上（多个时钟域相干处混合的核心）
export function addc(acc, r, g, b, w) { acc[0] += r * w; acc[1] += g * w; acc[2] += b * w; }

export function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// —— 单色青绿磷光辉：只靠亮度阶（迭代器 palette23 薄荷），整体提亮 ——
export function teal(e) {
  e = clamp(e, 0, 1); let r, g, b;
  if (e < 0.5) { const u = e / 0.5; r = 26 + 66 * u; g = 92 + 116 * u; b = 82 + 96 * u; }
  else { const u = (e - 0.5) / 0.5; r = 92 + 150 * u; g = 208 + 47 * u; b = 178 + 67 * u; }
  return [r, g, b];
}
// 把青底与某主题色按权重 w 混合（w=0 纯青，用于“相干处才上色”）
export function tint(rgb, hue, w) { w = clamp(w, 0, 1); return [rgb[0] + (hue[0] - rgb[0]) * w, rgb[1] + (hue[1] - rgb[1]) * w, rgb[2] + (hue[2] - rgb[2]) * w]; }

// —— 3D 线框投影（移植自参照，适配字符 ~1:1.8 高宽比）——
const TAU = Math.PI * 2, ASP = 0.5;
export function rot(x, y, z, t) {
  const a = t * 0.37, b = t * 0.23, ca = Math.cos(a), sa = Math.sin(a), cb = Math.cos(b), sb = Math.sin(b);
  const X = x * ca + z * sa, Z0 = z * ca - x * sa;
  const Y = y * cb - Z0 * sb, Z = Z0 * cb + y * sb;
  return [X, Y, Z];
}
export function project(x, y, z, cx, cy, scale) {
  const p = 3.7 / (3.7 + z);
  return [cx + x * scale * p, cy + y * scale * ASP * p, z];
}
export function torus(R, r, N, M) {
  const V = [], E = [];
  for (let i = 0; i < N; i++) { const u = i / N * TAU; for (let j = 0; j < M; j++) { const v = j / M * TAU;
    V.push([(R + r * Math.cos(v)) * Math.cos(u), r * Math.sin(v), (R + r * Math.cos(v)) * Math.sin(u)]);
    const a = i * M + j; E.push([a, ((i + 1) % N) * M + j]); E.push([a, i * M + ((j + 1) % M)]); } }
  return { V, E };
}

// —— 软件 3D：相机 + 透视投影 + painter 深度排序（字符按深度调暗）——
export function makeCam(elev, azim, dist, cx, cy, scale) {
  const ce = Math.cos(elev), se = Math.sin(elev), ca = Math.cos(azim), sa = Math.sin(azim);
  return {
    // 世界点 → 相机空间 [x右, y上, z朝屏幕内]
    view(x, y, z) {
      const x1 = x * ca - z * sa, z1 = x * sa + z * ca;         // 绕 y 转方位
      const y2 = y * ce - z1 * se, z2 = y * se + z1 * ce;       // 绕 x 转俯仰
      return [x1, y2, z2 + dist];
    },
    project(x, y, z) { const v = this.view(x, y, z); const p = scale / Math.max(0.2, v[2]); return [cx + v[0] * p, cy - v[1] * p * ASP, v[2]]; },
  };
}
