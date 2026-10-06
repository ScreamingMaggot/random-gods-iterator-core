// 数据层：pack.json 是渲染器唯一数据源。
// 解码写成纯函数 decodePack(obj)，浏览器与 node 校核脚本共用（node 用 readFileSync 得到 obj）。
const b64 = (s) => {
  const bin = atob(s);
  const u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return u;
};

export function decodePack(p) {
  const T = p.audio.nframes, fps = p.audio.fps, NB = p.audio.nbands;
  const ch = {};
  for (const [k, v] of Object.entries(p.audio.channels)) ch[k] = b64(v);
  const bands = b64(p.audio.bands);
  const power = b64(p.power_curve_b64);

  const frame = (t) => Math.max(0, Math.min(T - 1, Math.round(t * fps)));
  const get = (name, i) => (ch[name] ? ch[name][i] / 255 : 0);

  return {
    raw: p, T, fps, NB, ch, bands, power,
    frame,
    at: (name, t) => get(name, frame(t)),
    v: (name, f) => get(name, f),                 // 按帧索引取值
    band: (b, i) => bands[b * T + i] / 255,
    electric: (t) => power[frame(t)] / 255,
    electricF: (f) => power[f] / 255,
    actAt: (t) => p.acts.find((a) => t >= a.start && t < a.end) || p.acts[p.acts.length - 1],
    actAtFrame: (f) => {
      const t = f / fps;
      return p.acts.find((a) => t >= a.start && t < a.end) || p.acts[p.acts.length - 1];
    },
    palette: p.palette,
    map: p.map,
    engine: p.engine,
    events: p.events,
    beats: p.audio.beats,                          // 秒数组
    bpm: p.audio.tempo,
    bpm2: p.audio.second_clock_bpm,
    duration: p.audio.duration,
  };
}

export async function loadPack(url = "/out/pack.json") {
  const p = await (await fetch(url)).json();
  return decodePack(p);
}
