import base64, json
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)'

def b64(p):
    with open(p, 'rb') as f:
        return 'data:image/png;base64,' + base64.b64encode(f.read()).decode()

lvl = b64(root + '/resource/lt/ss_a01_1.png')
pal = b64(root + '/web/pals/palette23.png')
noise = b64(root + '/ref/shared/noise.png')
glyphs = b64(root + '/ref/shared/glyphs.png')

with open(root + '/resource/lt/index2.json', encoding='utf-8') as f:
    pmap = json.load(f)
ss = pmap.get('ss_a01', {'pal': 23, 'fade': 17})

with open(root + '/ref/placed.json', encoding='utf-8') as f:
    placed_all = json.load(f)
placed_ss = {'rooms': {'ss_a01': placed_all.get('rooms', {}).get('ss_a01', [])}}

html = open(root + '/web/glsl_preview.html', encoding='utf-8').read()

html = html.replace(
    'const pmap = await (await fetch("/resource/lt/index2.json")).json();',
    'const pmap = {"ss_a01": {"pal": %d, "fade": %d}};' % (ss['pal'], ss['fade']))
html = html.replace('load("/resource/lt/" + ROOM + "_1.png")', 'load(LEVEL_B64)')
html = html.replace('load("pals/palette" + rinfo.pal + ".png")', 'load(PAL_B64)')
html = html.replace('load("/ref/shared/noise.png")', 'load(NOISE_B64)')
html = html.replace('GLYPHS.src = "/ref/shared/glyphs.png";', 'GLYPHS.src = GLYPHS_B64;')
html = html.replace('if (!placed) placed = await (await fetch("/ref/placed.json")).json();',
                    'if (!placed) placed = PLACED;')

ins = ('const LEVEL_B64=%r, PAL_B64=%r, NOISE_B64=%r, GLYPHS_B64=%r;\n' % (lvl, pal, noise, glyphs)
       + 'const PLACED=' + json.dumps(placed_ss, separators=(',', ':')) + ';\n')
i = html.find('<script>')
html = html[:i + 8] + '\n' + ins + html[i + 8:]

out = root + '/web/glsl_preview_offline.html'
open(out, 'w', encoding='utf-8').write(html)
print('OK bytes', len(html), '->', out)
