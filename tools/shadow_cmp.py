import numpy as np
from PIL import Image
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/'
tex = np.array(Image.open(root + 'resource/lt/ss_a01_1.png').convert('RGB')).astype(np.float32)
noise = np.array(Image.open(root + 'ref/shared/noise.png').convert('RGB')).astype(np.float32)
pal = np.array(Image.open(root + 'web/pals/palette24.png').convert('RGB')).astype(np.float32)
H, W = tex.shape[:2]
NH, NW = noise.shape[:2]

red = np.floor(tex[..., 0] * 255 + 0.5)
m30 = np.mod(red, 30.0)
yy, xx = np.mgrid[0:H, 0:W]
u = (xx + 0.5) / W
v = (yy + 0.5) / H

def sample_noise(fu, fv, wrap):
    x = np.floor(fu * NW).astype(int)
    y = np.floor(fv * NH).astype(int)
    if wrap == 'repeat':
        x %= NW; y %= NH
    else:
        x = np.clip(x, 0, NW - 1); y = np.clip(y, 0, NH - 1)
    return noise[y, x, 0] / 255.0

for wrap in ('clamp', 'repeat'):
    n = sample_noise(u * 0.5 - 0.003 * m30, 1.0 - v * 0.5 - 0.003 * m30, wrap)
    shadow = 0.5 + np.sin(np.modf(n - v)[0] * 2 * np.pi) * 0.5
    shadow = np.clip((shadow - 0.5) * 6.0 + 0.5, 0.0, 1.0)
    r2 = np.where(red > 90, red - 90, red)
    shadow = np.where(red > 90, shadow, 1.0)
    pc = np.clip(np.floor((r2 - 1) / 30.0), 0, 2)
    depth = np.mod(r2 - 1, 30.0)
    lit = pal[np.clip(pc + 3, 0, 7).astype(int), np.clip(depth, 0, 31).astype(int)]
    sh = pal[pc.astype(int), np.clip(depth, 0, 31).astype(int)]
    out = lit * shadow[..., None] + sh * (1 - shadow[..., None])
    print('%-7s shadow mean %.3f | avg RGB %.1f %.1f %.1f -> %s' % (
        wrap, shadow.mean(), out[..., 0].mean(), out[..., 1].mean(), out[..., 2].mean(),
        'TEAL' if out[..., 1].mean() > out[..., 0].mean() else 'RED'))
    print('        row usage: r3 %.1f%%  r4 %.1f%%  r5 %.1f%%' % (
        100 * (pc + 3 == 3).mean(), 100 * (pc + 3 == 4).mean(), 100 * (pc + 3 == 5).mean()))
