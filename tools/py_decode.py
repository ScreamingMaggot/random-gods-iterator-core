import numpy as np
from PIL import Image
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/'

pal = np.array(Image.open(root + 'web/pals/palette24.png').convert('RGB')).astype(np.float32) / 255.0
tex = np.array(Image.open(root + 'resource/lt/ss_a01_1.png').convert('RGB')).astype(np.float32)
H, W = tex.shape[:2]

red = np.floor(tex[..., 0] * 255 + 0.5)
green = np.floor(tex[..., 1] * 255 + 0.5)

notFloorDark = np.ones_like(green)
m = green >= 16
notFloorDark[m] = 0.0
green[m] -= 16

effectCol = np.where(green >= 8, 100.0, green)
green = np.where(green >= 8, green - 8, green)

shadow = np.where(red > 90, 1.0, 0.0)  # no dynamic shadow: red<=90 -> shadow=1
r2 = np.where(red > 90, red - 90, red)

paletteColor = np.clip(np.floor((r2 - 1) / 30.0), 0, 2)
depth = np.mod(r2 - 1, 30.0)

def sample(col, row):
    col = np.clip(col, 0, 31)
    row = np.clip(row, 0, 7)
    return pal[row.astype(int), col.astype(int)]

# shadow=1 -> picks paletteColor+3 row (the shadowed variant in the real shader)
lit = sample(depth, paletteColor + 3)
shaded = sample(depth, paletteColor)
out = np.where((shadow > 0.5)[..., None], lit, shaded)

# skip effectCol==100 decal pixels (they pull colour from the atlas row)
eff = (effectCol == 100.0)
out[eff] = shaded[eff]

res = np.clip(out * 255, 0, 255).astype(np.uint8)
Image.fromarray(res).resize((480, 270), Image.NEAREST).save(root + 'out/py_decode_a01.png')

print("mean %.1f  p50 %.0f  p95 %.0f" % (res.mean(), np.percentile(res, 50), np.percentile(res, 95)))
r, g, b = res[..., 0].mean(), res[..., 1].mean(), res[..., 2].mean()
print("avg RGB: %.1f %.1f %.1f  -> %s" % (r, g, b, "TEAL/GREEN" if g > r else "RED/RED-DOMINANT"))
print("effectCol==100 share: %.1f%%" % (100 * eff.mean()))
print("saved out/py_decode_a01.png")
