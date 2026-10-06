import numpy as np
from PIL import Image
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/'
tex = np.array(Image.open(root + 'resource/lt/ss_e07_1.png').convert('RGB')).astype(int)
pal = np.array(Image.open(root + 'web/pals/palette23.png').convert('RGB')).astype(int)

print('raw channel stats:')
for i, nm in enumerate('RGB'):
    ch = tex[..., i]
    print('  %s: min %3d max %3d mean %6.1f  unique %d' % (nm, ch.min(), ch.max(), ch.mean(), len(np.unique(ch))))

R = tex[..., 0]
G = tex[..., 1]
B = tex[..., 2]

print()
print('R value histogram (top 12):')
u, c = np.unique(R, return_counts=True)
o = np.argsort(-c)[:12]
for i in o:
    print('   R=%3d : %6d px (%.1f%%)' % (u[i], c[i], 100 * c[i] / R.size))

print()
print('G value histogram (top 12):')
u2, c2 = np.unique(G, return_counts=True)
o2 = np.argsort(-c2)[:12]
for i in o2:
    print('   G=%3d : %6d px (%.1f%%)' % (u2[i], c2[i], 100 * c2[i] / R.size))

print()
print('B unique values:', np.unique(B)[:10], '... count', len(np.unique(B)))
print()
print('palette23 row0 (first 8):', ['%02x%02x%02x' % tuple(pal[0, c]) for c in range(8)])
print('palette23 row1 (first 8):', ['%02x%02x%02x' % tuple(pal[1, c]) for c in range(8)])
print('palette23 row2 (first 8):', ['%02x%02x%02x' % tuple(pal[2, c]) for c in range(8)])
print('palette23 row3 (first 8):', ['%02x%02x%02x' % tuple(pal[3, c]) for c in range(8)])
print('palette23 row4 (first 8):', ['%02x%02x%02x' % tuple(pal[4, c]) for c in range(8)])
print('palette23 row5 (first 8):', ['%02x%02x%02x' % tuple(pal[5, c]) for c in range(8)])
print('palette23 row7 (first 8):', ['%02x%02x%02x' % tuple(pal[7, c]) for c in range(8)])
