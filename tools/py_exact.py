import numpy as np
from PIL import Image
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/'

pal = np.array(Image.open(root + 'web/pals/palette24.png').convert('RGB')).astype(np.float32) / 255.0
tex = np.array(Image.open(root + 'resource/lt/ss_a01_1.png').convert('RGB')).astype(np.float32)
noise = np.array(Image.open(root + 'ref/shared/noise.png').convert('RGB')).astype(np.float32)

H, W = tex.shape[:2]
red = np.floor(tex[..., 0] * 255 + 0.5)
green = np.floor(tex[..., 1] * 255 + 0.5)

notFloorDark = np.where(green >= 16, 0.0, 1.0)
green = np.where(green >= 16, green - 16, green)
effectCol = np.where(green >= 8, 100.0, green)
green = np.where(green >= 8, green - 8, green)

m30 = np.mod(red, 30.0)
# GLSL noise lookup: uv.x*0.5 - 0.003*m30 , 1 - uv.y*0.5 - 0.003*m30, NEAREST, CLAMP
def noise_at(u, v):
    x = np.clip((u * noise.shape[1]).astype(int), 0, noise.shape[1] - 1)
    y = np.clip((v * noise.shape[0]).astype(int), 0, noise.shape[0] - 1)
    return noise[y, x, 0] / 255.0

yy, xx = np.mgrid[0:H, 0:W]
u = xx / W
v = yy / H
n = noise_at(u * 0.5 - 0.003 * m30, 1.0 - v * 0.5 - 0.003 * m30)
shadow = 0.5 + np.sin(np.modf(n - v)[0] * 6.2831853) * 0.5
LIGHT = 0.0
shadow = np.clip((shadow - 0.5) * 6.0 + 0.5 - LIGHT * 4.0, 0.0, 1.0)

red2 = red.copy()
shadow = np.where(red > 90, shadow, 1.0)
r2 = np.where(red > 90, red - 90, red)
pc = np.clip(np.floor((r2 - 1) / 30.0), 0, 2)
depth = np.mod(r2 - 1, 30.0)

def sample(c, r):
    c = np.clip(c, 0, 31); r = np.clip(r, 0, 7)
    return pal[r.astype(int), c.astype(int)]

lit = sample(depth, pc + 3.0)
shaded = sample(depth, pc)
out = lit * shadow[..., None] + shaded * (1 - shadow[..., None])

# fog: fogCol = pal(1,7); mix by clamp(red*uFog/30) with uFog=1
FOG = 1.0
fogcol = sample(np.ones_like(depth), np.full_like(depth, 7.0))
out = out * (1 - np.clip(depth * FOG / 30.0, 0, 1)[..., None]) + fogcol * np.clip(depth * FOG / 30.0, 0, 1)[..., None]

eff = (effectCol == 100.0)
print("effectCol==100 share: %.1f%%" % (100 * eff.mean()))
res = np.clip(out * 255, 0, 255).astype(np.uint8)
Image.fromarray(res).resize((480, 270), Image.NEAREST).save(root + 'out/py_exact_a01.png')
r, g, b = res[..., 0].mean(), res[..., 1].mean(), res[..., 2].mean()
print("mean %.1f p50 %.0f p95 %.0f" % (res.mean(), np.percentile(res, 50), np.percentile(res, 95)))
print("avg RGB %.1f %.1f %.1f -> %s" % (r, g, b, "TEAL" if g > r else "RED"))
