from PIL import Image, ImageDraw
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/out/'
a = Image.open(root + 'ab_ed0.png').convert('RGB').crop((0, 30, 480, 300))
b = Image.open(root + 'ab_ed45.png').convert('RGB').crop((0, 30, 480, 300))
w, h = a.size
out = Image.new('RGB', (w * 2 + 12, h + 26), (12, 12, 14))
out.paste(a, (0, 26))
out.paste(b, (w + 12, 26))
d = ImageDraw.Draw(out)
d.text((6, 8), "ELEM_D=0  (no occlusion)", fill=(120, 230, 255))
d.text((w + 18, 8), "ELEM_D=0.45  (CustomDepth occlusion)", fill=(255, 210, 90))
out.save(root + 'ab_compare.png')
print('saved ab_compare.png', out.size)
