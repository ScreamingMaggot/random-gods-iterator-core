import base64, io, json, re
import numpy as np
from PIL import Image
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/'

# Pull the two PNGs the browser sees, and decode with the exact GLSL logic in numpy,
# but this time compute the SHADER'S pal() semantics directly from GL conventions.
pal_img = np.array(Image.open(root + 'web/pals/palette24.png').convert('RGB')).astype(np.float32) / 255.0
tex = np.array(Image.open(root + 'resource/lt/ss_a01_1.png').convert('RGB')).astype(np.float32)
H, W = tex.shape[:2]
NH, NW = 8, 32

def pal_glsl(c, r):
    """Exactly the GLSL:
         col = clamp(floor(c),0,31); row = clamp(7.0-floor(r),0,7);
         uv = ((col+0.5)/32, (row+0.5)/8)
       GL texture from a PNG: uv.y=0 -> PNG row 7, uv.y=1 -> PNG row 0
       => PNG row = 7 - floor((row+0.5)) = 7 - row - ... careful:
          uv.y=(row+0.5)/8 ; PNG_row = round((1-uv.y)*8 - 0.5) = round(8 - (row+0.5) - 0.5) = 7-row
    """
    c = np.clip(np.floor(c), 0, 31)
    r = np.clip(7.0 - np.floor(r), 0, 7)
    png_row = np.clip((7 - r).astype(int), 0, 7)
    return pal_img[png_row, c.astype(int)]

red = np.floor(tex[..., 0] * 255 + 0.5)
green = np.floor(tex[..., 1] * 255 + 0.5)
nf = np.where(green >= 16, 0.0, 1.0)
green = np.where(green >= 16, green - 16, green)
effectCol = np.where(green >= 8, 100.0, green)
green = np.where(green >= 8, green - 8, green)

yy, xx = np.mgrid[0:H, 0:W]
u = (xx + 0.5) / W
v = (yy + 0.5) / H

# NOISE: the browser samples a GL texture from a PNG -> also bottom-left flipped!
noise = np.array(Image.open(root + 'ref/shared/noise.png').convert('RGB')).astype(np.float32)
def noise_glsl(fu, fv):
    fx = np.clip((fu * NW).astype(int), 0, NW - 1)
    # GL: uv.y=0 -> PNG bottom row (NH-1)
    fy_gl = np.clip((fv * NH).astype(int), 0, NH - 1)
    fy = NH - 1 - fy_gl
    return noise[fy, fx, 0] / 255.0

m30 = np.mod(red, 30.0)
n = noise_glsl(u * 0.5 - 0.003 * m30, 1.0 - v * 0.5 - 0.003 * m30)
shadow = 0.5 + np.sin(np.modf(n - v)[0] * 2 * np.pi) * 0.5
shadow = np.clip((shadow - 0.5) * 6.0 + 0.5 - 0.0, 0.0, 1.0)
shadow = np.where(red > 90, shadow, 1.0)
r2 = np.where(red > 90, red - 90, red)
pc = np.clip(np.floor((r2 - 1) / 30.0), 0, 2)
depth = np.mod(r2 - 1, 30.0)

fogCol = pal_glsl(np.ones_like(depth), np.full_like(depth, 7.0))
col = pal_glsl(depth * nf, pc + 3.0) * shadow[..., None] + pal_glsl(depth * nf, pc) * (1 - shadow[..., None])
rb = np.sin((noise_glsl(u * 2, v * 2) * 4 + depth / 12.0) * 2 * np.pi) * 0.5 + 0.5
ga = np.where(green >= 4, 0.2, 0.0)
col = col * (1 - ga[..., None]) + pal_glsl(5.5 + rb * 25.0, 6.0) * ga[..., None]
fa = np.clip(depth * FOG_ if (FOG_ := 1.0) else 0, 0, 1)
col = col * (1 - fa[..., None]) + fogCol * fa[..., None]

res = np.clip(col * 255, 0, 255).astype(np.uint8)
Image.fromarray(res).resize((480, 270), Image.NEAREST).save(root + 'out/py_glsl_faithful.png')
print("avg RGB %.1f %.1f %.1f -> %s" % (res[..., 0].mean(), res[..., 1].mean(), res[..., 2].mean(),
      'TEAL' if res[..., 1].mean() > res[..., 0].mean() else 'RED'))
print("fogCol =", '%02x%02x%02x' % tuple((fogCol[0, 0] * 255).astype(int)))
