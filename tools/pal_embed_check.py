import base64, io
import numpy as np
from PIL import Image
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/'
h = open(root + 'web/glsl_preview_offline.html', encoding='utf-8').read()
i = h.find('PALS={')
key = '"24": "'
j = h.find(key, i)
start = j + len(key)
end = h.find('"', start)
url = h[start:end]
raw = base64.b64decode(url.split(',', 1)[1])
im = Image.open(io.BytesIO(raw))
print('embedded palette24 size:', im.size, 'mode:', im.mode)
a = np.array(im.convert('RGB'))
for r in (0, 2, 5):
    print('embedded row%d:' % r, ['%02x%02x%02x' % tuple(p) for p in a[r, ::3][:10]])

disk = np.array(Image.open(root + 'web/pals/palette24.png').convert('RGB'))
print()
for r in (0, 2, 5):
    print('disk     row%d:' % r, ['%02x%02x%02x' % tuple(p) for p in disk[r, ::3][:10]])
print()
print('embedded shape', a.shape, ' disk shape', disk.shape,
      ' identical:', a.shape == disk.shape and (a == disk).all())
