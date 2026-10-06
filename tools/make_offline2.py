import base64, json
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)'
ROOMS = ['ss_a01', 'ss_e07', 'ss_l01', 'ss_f01']

def b64(p):
    with open(p, 'rb') as f:
        return 'data:image/png;base64,' + base64.b64encode(f.read()).decode()

levels = {r: b64(root + '/resource/lt/%s_1.png' % r) for r in ROOMS}
noise = b64(root + '/ref/shared/noise.png')
glyphs = b64(root + '/ref/shared/glyphs.png')

index = json.load(open(root + '/resource/lt/index2.json', encoding='utf-8'))
pmap = {r: index.get(r, {'pal': 23, 'fade': 17}) for r in ROOMS}
pals = {}
for r in ROOMS:
    p = pmap[r]['pal']
    if p not in pals:
        pals[p] = b64(root + '/web/pals/palette%d.png' % p)

placed_all = json.load(open(root + '/ref/placed.json', encoding='utf-8'))
placed = {'rooms': {r: placed_all.get('rooms', {}).get(r, []) for r in ROOMS}}

html = open(root + '/web/glsl_preview.html', encoding='utf-8').read()
html = html.replace('const pmap = await (await fetch("/resource/lt/index2.json")).json();',
                    'const pmap = PMAP;')
html = html.replace('load("/resource/lt/" + ROOM + "_1.png")', 'load(LEVELS[ROOM])')
html = html.replace('load("pals/palette" + rinfo.pal + ".png")', 'load(PALS[rinfo.pal])')
html = html.replace('load("/ref/shared/noise.png")', 'load(NOISE_B64)')
html = html.replace('GLYPHS.src = "/ref/shared/glyphs.png";', 'GLYPHS.src = GLYPHS_B64;')
html = html.replace('if (!placed) placed = await (await fetch("/ref/placed.json")).json();',
                    'if (!placed) placed = PLACED;')

ins = ('const LEVELS=%s, PALS=%s, PMAP=%s, PLACED=%s, NOISE_B64=%r, GLYPHS_B64=%r;\n' % (
    json.dumps(levels), json.dumps(pals), json.dumps(pmap),
    json.dumps(placed, separators=(',', ':')), noise, glyphs))
i = html.find('<script>')
html = html[:i + 8] + '\n' + ins + html[i + 8:]

out = root + '/web/glsl_preview_offline.html'
open(out, 'w', encoding='utf-8').write(html)
print('OK bytes', len(html), '| rooms:', ', '.join(ROOMS), '| palettes:', sorted(pals))
