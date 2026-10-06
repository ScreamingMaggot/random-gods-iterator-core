import numpy as np
from PIL import Image
a = np.array(Image.open(r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/resource/lt/ss_a01_1.png').convert('RGB'))
R = a[..., 0].astype(int)
depth = (R - 1) % 30
h = np.bincount(depth.ravel(), minlength=30)
print("depth hist 0..29:", h.tolist())
for E in (0.1, 0.2, 0.3, 0.45, 0.6, 0.8):
    occ = (depth / 30.0 < E).mean()
    print("ELEM_D=%.2f -> blocked %.1f%% of pixels" % (E, occ * 100))
