import os, re, json
root = r'd:/Entertainments/steam2/steamapps/common/Rain World/RainWorld_Data/StreamingAssets/world/ss-rooms'
out = {}
for fn in os.listdir(root):
    if not fn.endswith('_settings.txt'):
        continue
    key = fn[:-len('_settings.txt')].lower()
    txt = open(os.path.join(root, fn), encoding='utf-8', errors='replace').read()
    pal = re.search(r'^Palette:\s*(\d+)', txt, re.M)
    fade = re.search(r'^FadePalette:\s*(\d+)', txt, re.M)
    out[key] = {'pal': int(pal.group(1)) if pal else 23,
                'fade': int(fade.group(1)) if fade else 17}
dst = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/resource/lt/index2.json'
json.dump(out, open(dst, 'w', encoding='utf-8'), indent=0, sort_keys=True)
print("wrote", len(out), "rooms ->", dst)
for k in ['ss_a01', 'ss_i01', 'ss_l01', 'ss_d04']:
    print(" ", k, out.get(k))
