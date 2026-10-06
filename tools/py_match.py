import numpy as np
from PIL import Image
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/'

pal = np.array(Image.open(root + 'web/pals/palette24.png').convert('RGB')).astype(np.float32) / 255.0
tex = np.array(Image.open(root + 'resource/lt/ss_a01_1.png').convert('RGB')).astype(np.float32)
noise = np.array(Image.open(root + 'ref/shared/noise.png').convert('RGB')).astype(np.float32)
H, W = tex.shape[:2]
NH, NW = noise.shape[:2]

def P(c, r):
    """Mimic the FIXED GLSL pal().

    GLSL: row' = 7 - floor(r); uv.y = (row'+0.5)/8
    A GL texture uploaded from a PNG has origin at bottom-left, so uv.y=0
    is the PNG's LAST row. uv.y=(7+0.5)/8 -> PNG row 0.
    Therefore: PNG_row = floor(r).
    """
    c = np.clip(np.floor(c), 0, 31)
    row = np.clip(np.floor(r), 0, 7)
    y = np.clip(row.astype(int), 0, 7)
    x = np.clip(c.astype(int), 0, 31)
    return pal[y, x]

red = np.floor(tex[..., 0] * 255 + 0.5)
green = np.floor(tex[..., 1] * 255 + 0.5)
notFloorDark = np.where(green >= 16, 0.0, 1.0)
green = np.where(green >= 16, green - 16, green)
effectCol = np.where(green >= 8, 100.0, green)
green = np.where(green >= 8, green - 8, green)

m30 = np.mod(red, 30.0)
yy, xx = np.mgrid[0:H, 0:W]
u = (xx + 0.5) / W
v = (yy + 0.5) / H
def noise_at(fu, fv):
    x = np.clip((fu * NW).astype(int), 0, NW - 1)
    y = np.clip((fv * NH).astype(int), 0, NH - 1)
    return noise[y, x, 0] / 255.0
n = noise_at(u * 0.5 - 0.003 * m30, 1.0 - v * 0.5 - 0.003 * m30)
shadow = 0.5 + np.sin(np.modf(n - v)[0] * 2 * np.pi) * 0.5
shadow = np.clip((shadow - 0.5) * 6.0 + 0.5, 0.0, 1.0)
shadow = np.where(red > 90, shadow, 1.0)
r2 = np.where(red > 90, red - 90, red)
pc = np.clip(np.floor((r2 - 1) / 30.0), 0, 2)
depth = np.mod(r2 - 1, 30.0)

fogCol = P(np.ones_like(depth), np.full_like(depth, 7.0))
col = P(depth * notFloorDark, pc + 3.0) * shadow[..., None] + \
      P(depth * notFloorDark, pc) * (1 - shadow[..., None])

GRIME = 1.0
rb = np.sin((noise_at(u * 2, v * 2) * 4 + depth / 12.0) * 2 * np.pi) * 0.5 + 0.5
grime_amt = np.where(green >= 4, 0.2, 0.0) * GRIME
col = col * (1 - grime_amt[..., None]) + P(5.5 + rb * 25.0, 6.0) * grime_amt[..., None]

eff = (effectCol == 100.0)
# decal: sample the same texture; emulate the texel fetch
bx = np.clip(((255.5 - tex[..., 2] * 255.0) / 1400.0 * W).astype(int), 0, W - 1)
by = int(np.clip(799.5 / 800.0 * H, 0, H - 1))
dc_raw = tex[by, bx] / 255.0
dc = np.where((pc == 2.0)[..., None], dc_raw * (1 - (0.2 - shadow * 0.1)[..., None]) + 1.0 * (0.2 - shadow * 0.1)[..., None], dc_raw)
dc = dc * (1 - (depth / 60.0)[..., None]) + fogCol * (depth / 60.0)[..., None]
c2 = col * (1 - 0.7) + dc * 0.7
w2 = np.clip(0.9, 0, 1)  # placeholder, real: mix(0.9, 0.3+0.4*shadow, saturate((depth-3.5)*0.3))
t2 = np.clip((depth - 3.5) * 0.3, 0, 1)
w2 = 0.9 * (1 - t2) + (0.3 + 0.4 * shadow) * t2
mul = np.clip(col * dc * 1.5, 0, 4)
col_eff = c2 * (1 - w2[..., None]) + mul * w2[..., None]
col = np.where(eff[..., None], col_eff, col)

FOG = 1.0
fa = np.clip(depth * (np.where(depth < 10, notFloorDark * 0.5 + 0.5, 1.0)) * FOG / 30.0, 0, 1)
col = col * (1 - fa[..., None]) + fogCol * fa[..., None]

res = np.clip(col * 255, 0, 255).astype(np.uint8)
Image.fromarray(res).resize((480, 270), Image.NEAREST).save(root + 'out/py_match.png')
print("avg RGB %.1f %.1f %.1f -> %s" % (res[..., 0].mean(), res[..., 1].mean(), res[..., 2].mean(),
      'TEAL' if res[..., 1].mean() > res[..., 0].mean() else 'RED'))
print("mean %.1f p50 %.0f p95 %.0f" % (res.mean(), np.percentile(res, 50), np.percentile(res, 95)))
print("saved out/py_match.png")
