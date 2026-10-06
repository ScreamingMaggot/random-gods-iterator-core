import { loadPack } from "./src/pack.js";
import { createCPU } from "./src/cpu.js";
import { createCpuAscii } from "./src/cpuascii.js";

const AUDIO = "/resource/" + encodeURIComponent("Random Gods (Theme III) - James Primate.mp3");
const params = new URLSearchParams(location.search);

async function boot() {
  const canvas = document.getElementById("stage");
  const errEl = document.getElementById("err");
  const gate = document.getElementById("gate");
  const loading = document.getElementById("loading");

  if (location.protocol === "file:") {
    loading.style.display = "none"; gate.style.display = "flex";
    errEl.textContent = "请用本地服务打开（file:// 会拦下 pack.json）：python tools/serve.py 8712 → http://127.0.0.1:8712/ascii/";
    return;
  }
  try {
    const pack = await loadPack("/out/pack.json");
    const cpu = createCPU(pack);
    const view = createCpuAscii(cpu, pack);
    const fit = () => view.resize(Math.min(innerWidth, 1500), Math.min(innerHeight, 900));
    fit(); addEventListener("resize", fit);

    const clampT = (t) => Math.max(0, Math.min(pack.duration, t || 0));
    let curTick = 0;
    const seek = (t) => { const target = Math.round(clampT(t) * pack.fps); cpu.simToFrame(target); curTick = target; view.draw(cpu.state, cpu.metrics()); };
    window.__seek = seek;
    // 逐帧出片钩子：__reset 归零、__step 前进一帧(1/30s)并重绘，返回当前帧号
    window.__frames = pack.T;
    window.__reset = () => { cpu.simToFrame(0); curTick = 0; view.draw(cpu.state, cpu.metrics()); return curTick; };
    window.__step = () => { if (curTick < pack.T - 1) { cpu.tick(curTick); curTick++; } view.draw(cpu.state, cpu.metrics()); return curTick; };

    const audio = new Audio(AUDIO); audio.preload = "auto"; audio.volume = 0.9;
    let playing = false;
    const loop = () => {
      try {
        if (playing) { const target = Math.min(pack.T - 1, Math.round(audio.currentTime * pack.fps));
          if (Math.abs(target - curTick) > pack.fps * 1.5) { cpu.simToFrame(target); curTick = target; }   // 起播脱同步/跳转：直接重算到目标帧
          else { while (curTick < target) { cpu.tick(curTick); curTick++; } }
          view.draw(cpu.state, cpu.metrics()); }
      } catch (e) { errEl.textContent = "帧错误(已跳过): " + (e && e.message || e); }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);

    window.__ready = true; loading.style.display = "none";

    if (params.has("auto")) { seek(parseFloat(params.get("t") || "0")); return; }

    if (params.has("record")) {   // 出片：MediaRecorder 实时录 canvas（30fps），事后用 ffmpeg 合音轨
      const FPS = +(params.get("fps") || 30);
      cpu.simToFrame(0); curTick = 0; view.draw(cpu.state, cpu.metrics());
      const stream = canvas.captureStream(FPS);
      let mime = "video/webm;codecs=vp9"; if (!MediaRecorder.isTypeSupported(mime)) mime = "video/webm";
      const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 16000000 });
      const chunks = []; rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      rec.onstop = () => { const blob = new Blob(chunks, { type: "video/webm" });
        const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "random_gods.webm"; document.body.appendChild(a); a.click(); window.__recDone = true; };
      const total = params.has("secs") ? Math.min(pack.T, Math.round(+params.get("secs") * FPS)) : pack.T; const t0 = performance.now(); rec.start(); window.__recStart = true;
      const step = () => { const el = (performance.now() - t0) / 1000; const target = Math.min(total - 1, Math.round(el * FPS));
        while (curTick < target) { cpu.tick(curTick); curTick++; } view.draw(cpu.state, cpu.metrics());
        if (curTick >= total - 1) { rec.stop(); return; } requestAnimationFrame(step); };
      requestAnimationFrame(step);
      return;
    }

    seek(30); gate.style.display = "flex";   // 预览帧垫在门后
    const go = async () => {
      gate.style.display = "none";
      canvas.style.opacity = "0";
      requestAnimationFrame(() => { canvas.style.transition = "opacity 2s linear"; canvas.style.opacity = "1"; });   // 前两秒画面渐显
      seek(0); audio.currentTime = 0;
      try { await audio.play(); playing = true; } catch (e) { errEl.textContent = "音频被拦截，可用 ?auto=1&t=60 看单帧：" + e.message; }
      addEventListener("keydown", (ev) => {
        if (ev.key === " ") { playing ? audio.pause() : audio.play(); }
        if (ev.key === "ArrowRight") { audio.currentTime = clampT(audio.currentTime + 2); seek(audio.currentTime); }
        if (ev.key === "ArrowLeft") { audio.currentTime = clampT(audio.currentTime - 2); seek(audio.currentTime); }
      });
    };
    gate.addEventListener("click", go);
    audio.addEventListener("ended", () => { playing = false; seek(pack.duration - 0.2); });
  } catch (e) { loading.style.display = "none"; errEl.textContent = "启动失败: " + (e && e.stack || e); }
}
boot();
