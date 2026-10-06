p = r'd:\Entertainments\steam2\steamapps\common\Rain World\RainWorld_Data\StreamingAssets\world\ss-rooms\ss_i01.txt'
d = open(p, encoding='utf-8', errors='replace').read()
print('total len', len(d))
lines = d.split('\n')
print('line count', len(lines))
for i, l in enumerate(lines[:8]):
    print(i, 'len=%d' % len(l), repr(l[:160]))
print('---- tail ----')
for i, l in enumerate(lines[-4:]):
    print('end', repr(l[:160]))
