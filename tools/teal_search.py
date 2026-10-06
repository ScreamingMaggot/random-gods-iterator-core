import os
import numpy as np
from PIL import Image
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/'
tex = np.array(Image.open(root + 'resource/lt/ss_a01_1.png').convert('RGB')).astype(int)
R = tex[..., 0]
red = R.copy()
r2 = np.where(red > 90, red - 90, red)
pc = np.clip(np.floor((r2 - 1) / 30.0), 0, 2).astype(int)
depth = np.clip(np.mod(r2 - 1, 30.0), 0, 31).astype(int)
nf = np.where(tex[..., 1] >= 16, 0, 1).astype(int)
dcol = np.where(nf == 0, 0, depth)

print("palette  litRow(pal[pc])        shadowRow(pal[pc+3])     verdict")
for p in range(9, 30):
    fp = root + 'web/pals/palette%d.png' % p
    if not os.path.exists(fp):
        continue
    pal = np.array(Image.open(fp).convert('RGB')).astype(float)
    lit = pal[pc, dcol]
    sh = pal[np.clip(pc + 3, 0, 7), dcol]
    lr, lg, lb = lit[..., 0].mean(), lit[..., 1].mean(), lit[..., 2].mean()
    sr, sg, sb = sh[..., 0].mean(), sh[..., 1].mean(), sh[..., 2].mean()
    # gray-teal: g>r, b>=r, and not too saturated
    def tealish(r, g, b):
        return g > r + 5 and b > r + 2 and max(r, g, b) - min(r, g, b) < 90
    v = 'GRAY-TEAL lit' if tealish(lr, lg, lb) else ('teal-ish lit' if lg > lr else '')
    v2 = 'GRAY-TEAL shadow' if tealish(sr, sg, sb) else ''
    print("  %-3d   %5.1f %5.1f %5.1f %-14s %5.1f %5.1f %5.1f %s" % (p, lr, lg, lb, v, sr, sg, sb, v2))
