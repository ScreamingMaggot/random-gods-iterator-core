import os, re, json
import numpy as np
from PIL import Image
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/'
srdir = r'd:/Entertainments/steam2/steamapps/common/Rain World/RainWorld_Data/StreamingAssets/world/ss-rooms'

# palette 23/24 rows 2-3 are teal; 13 is warm gray. Which palettes have teal rows?
print("=== palette teal check (row2, col10) ===")
teal_pals = []
for p in range(9, 30):
    fp = root + 'web/pals/palette%d.png' % p
    if not os.path.exists(fp):
        continue
    a = np.array(Image.open(fp).convert('RGB')).astype(int)
    r, g, b = a[2, 10]
    tag = 'TEAL' if g > r + 15 else ('RED' if r > g + 15 else 'neutral')
    if tag == 'TEAL':
        teal_pals.append(p)
    print("  palette%-3d row2 col10 = %02x%02x%02x  %s" % (p, r, g, b, tag))
print()
print("teal palettes:", teal_pals)

# which rooms use them
print()
print("=== rooms using teal palettes ===")
for fn in sorted(os.listdir(srdir)):
    if not fn.endswith('_settings.txt'):
        continue
    txt = open(os.path.join(srdir, fn), encoding='utf-8', errors='replace').read()
    m = re.search(r'^Palette:\s*(\d+)', txt, re.M)
    if m and int(m.group(1)) in teal_pals:
        print("  %-14s palette %s" % (fn[:-13], m.group(1)))
