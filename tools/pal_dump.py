import numpy as np
from PIL import Image
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/web/pals/'
for name in ['palette13.png', 'palette23.png', 'palette17.png']:
    im = Image.open(root + name).convert('RGB')
    a = np.array(im)
    h, w = a.shape[:2]
    print("=== %s  %dx%d ===" % (name, w, h))
    for row in range(h):
        cells = []
        for col in [0, 5, 10, 15, 20, 25, 30]:
            if col < w:
                r, g, b = a[row, col]
                cells.append("%02x%02x%02x" % (r, g, b))
        print("  row%d: %s" % (row, " ".join(cells)))
