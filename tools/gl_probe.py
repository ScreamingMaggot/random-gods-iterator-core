import subprocess, sys, json
# Read pixels straight out of the running WebGL canvas via playwright
js = """
(() => {
  const c = document.getElementById('cv');
  const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
  const w = c.width, h = c.height;
  const px = new Uint8Array(w*h*4);
  gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,px);
  let r=0,g=0,b=0;
  for (let i=0;i<px.length;i+=4){r+=px[i];g+=px[i+1];b+=px[i+2];}
  const n = w*h;
  return {w:w,h:h,r:(r/n).toFixed(1),g:(g/n).toFixed(1),b:(b/n).toFixed(1)};
})()
"""
r = subprocess.run(['playwright-cli','eval',js], capture_output=True, text=True)
print(r.stdout[-2000:])
print(r.stderr[-2000:])
