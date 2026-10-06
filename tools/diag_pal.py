import base64, json, re
root = r'c:/Users/Administrator/Desktop/剪辑/数字艺术/20261006(3)/'
h = open(root + 'web/glsl_preview_offline.html', encoding='utf-8').read()
m = re.search(r'PALS=(\{.*?\}),\s*PMAP=', h, re.S)
if not m:
    idx = h.find('PALS=')
    print('context:', repr(h[idx:idx + 120]))
    raise SystemExit(1)
pals = json.loads(m.group(1))
for k, v in pals.items():
    raw = base64.b64decode(v.split(',', 1)[1])
    p = root + 'out/pal_%s.png' % k
    open(p, 'wb').write(raw)
    print('palette', k, '-> bytes', len(raw))
