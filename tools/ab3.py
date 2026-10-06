from PIL import Image, ImageDraw
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/out/'
rooms = [('ss_d04', '17 depth layers'), ('ss_i01', '16 layers, palette13'), ('ss_l01', '15 layers')]
tiles = []
for name, cap in rooms:
    im = Image.open(root + 'room_%s.png' % name).convert('RGB').crop((0, 30, 480, 300))
    tiles.append((im, cap))
w, h = tiles[0][0].size
out = Image.new('RGB', (w, (h + 22) * len(tiles)), (12, 12, 14))
d = ImageDraw.Draw(out)
for i, (im, cap) in enumerate(tiles):
    y = i * (h + 22)
    d.text((6, y + 6), "%s   %s" % (tiles[i][0] and cap, ''), fill=(255, 210, 90))
    out.paste(im, (0, y + 22))
out.save(root + 'rooms_triple.png')
print('saved rooms_triple.png', out.size)
