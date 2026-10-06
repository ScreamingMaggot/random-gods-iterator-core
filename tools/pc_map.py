import numpy as np
from PIL import Image
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/'
a = np.array(Image.open(root + 'resource/lt/ss_a01_1.png').convert('RGB')).astype(int)
R = a[..., 0]
red = R.copy()
r2 = np.where(red > 90, red - 90, red)
pc = np.clip(np.floor((r2 - 1) / 30.0), 0, 2).astype(np.uint8)
# false colour: pc0=red, pc1=green, pc2=blue, and mark red>90 in white
img = np.zeros(a.shape[:2] + (3,), np.uint8)
img[..., 0] = np.where(pc == 0, 255, 0)
img[..., 1] = np.where(pc == 1, 255, 0)
img[..., 2] = np.where(pc == 2, 255, 0)
Image.fromarray(img).resize((480, 270), Image.NEAREST).save(root + 'out/pc_map.png')
for v in range(3):
    print('pc=%d -> %.1f%%' % (v, 100 * (pc == v).mean()))
print('saved out/pc_map.png  (R=pc0, G=pc1, B=pc2)')
