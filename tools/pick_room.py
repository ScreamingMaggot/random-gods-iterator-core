import numpy as np, glob, os
from PIL import Image
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/resource/lt'
rows = []
for p in glob.glob(root + '/*_1.png'):
    name = os.path.basename(p)[:-6]
    a = np.array(Image.open(p).convert('RGB'))
    R = a[..., 0].astype(int)
    d = (R - 1) % 30
    h = np.bincount(d.ravel(), minlength=30).astype(float)
    h /= h.sum()
    layers = int((h > 0.02).sum())          # 有实际面积的深度层数
    ent = float(-(h[h > 0] * np.log(h[h > 0])).sum())
    rows.append((name, layers, ent))
rows.sort(key=lambda r: (-r[1], -r[2]))
print("room    depth_layers  entropy")
for n, l, e in rows[:18]:
    print("%-8s %5d        %.3f" % (n, l, e))
