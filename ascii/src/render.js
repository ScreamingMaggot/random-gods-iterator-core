// 渲染：95×55 字符 lattice 逐格 fillText（跳过空格），按颜色量化微批减少状态切换。
// 全片字面 ASCII 等宽；中文只进 HUD 文本行，不进网格。
const BG = "#04070a";
const FONT = "'DejaVu Sans Mono','Consolas','Courier New',monospace";

export function makeRenderer(sim, canvas) {
  const ctx = canvas.getContext("2d");
  const { COLS, ROWS, N } = sim;
  let W = 0, H = 0, cw = 1, chh = 1, ox = 0, oy = 0, ox2 = 0, lh = 1;
  const hx = (n) => (n | 0).toString(16).toUpperCase();

  function resize(w, h) {
    W = w; H = h; canvas.width = w; canvas.height = h;
    const hudH = 7;                                   // 底部留 7 行文字
    chh = Math.floor((h * 0.99) / (ROWS + hudH));
    cw = Math.floor((w * 0.985) / COLS);
    lh = chh;
    ox = Math.floor((w - cw * COLS) / 2);
    oy = Math.floor(chh * 0.4);
    ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
  }

  function draw(st) {
    ctx.fillStyle = BG; ctx.fillRect(0, 0, W, H);
    const fs = Math.max(6, Math.floor(chh * 0.86));
    ctx.font = `${fs}px ${FONT}`;
    const { gCh, gR, gG, gB, gA } = sim;
    let last = "";
    for (let p = 0; p < N; p++) {
      const code = gCh[p]; if (code === 32) continue;
      const a = gA[p]; if (a < 6) continue;
      const x = p % COLS, y = (p / COLS) | 0;
      // 量化到 4 位 alpha 桶以少改 fillStyle
      const ab = (a >> 4) << 4;
      const style = `rgba(${gR[p]},${gG[p]},${gB[p]},${Math.min(255, ab) / 255})`;
      if (style !== last) { ctx.fillStyle = style; last = style; }
      ctx.fillText(String.fromCharCode(code), ox + (x + 0.5) * cw, oy + (y + 0.82) * chh);
    }
    drawHud(st);
  }

  function drawHud(st) {
    const lines = sim.renderLines(st);
    const leg = "域 时钟域→色: ";
    const chips = sim.DOMS.map((d) => `${d.key}:${d.label}`);
    ctx.font = `${Math.max(9, Math.floor(chh * 0.9))}px ${FONT}`;
    ctx.textAlign = "left";
    const baseY = oy + ROWS * chh + chh;
    ctx.fillStyle = "#9fb4b0";
    lines.forEach((ln, i) => ctx.fillText(ln, ox + 2, baseY + i * lh));
    // 域色标尺（第 4 行）
    let cx = ox + 2, cy = baseY + 3 * lh;
    ctx.fillStyle = "#7c8f8b"; ctx.fillText("时钟域→色", cx, cy); cx += ctx.measureText("时钟域→色").width + 8;
    sim.DOMS.forEach((d) => {
      ctx.fillStyle = `rgb(${d.color[0]},${d.color[1]},${d.color[2]})`;
      ctx.fillRect(cx, cy - chh * 0.6, chh * 0.7, chh * 0.7); cx += chh;
      const s = `${d.key} ${st.S[d.key].ph.toFixed(0)}`;
      ctx.fillText(s, cx, cy); cx += ctx.measureText(s).width + 10;
    });
    ctx.textAlign = "center";
  }

  return { resize, draw };
}
