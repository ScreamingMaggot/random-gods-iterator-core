import os, re
srdir = r'd:/Entertainments/steam2/steamapps/common/Rain World/RainWorld_Data/StreamingAssets/world/ss-rooms'
rows = []
for fn in sorted(os.listdir(srdir)):
    if not fn.endswith('_settings.txt'):
        continue
    key = fn[:-len('_settings.txt')]
    txt = open(os.path.join(srdir, fn), encoding='utf-8', errors='replace').read()
    pal = re.search(r'^Palette:\s*(\d+)', txt, re.M)
    pal = int(pal.group(1)) if pal else -1
    eff = re.search(r'^Effects:\s*(.*)$', txt, re.M)
    eff = eff.group(1) if eff else ''
    bloom = re.search(r'Bloom-([\d.]+)', eff)
    bloom = float(bloom.group(1)) if bloom else 0.0
    ncc = txt.count('CoralCircuit')
    ncn = txt.count('CoralNeuron')
    nss = txt.count('SuperStructureProjector')
    npsl = txt.count('ProjectedScanLines')
    nwm = txt.count('WallMycelia')
    rows.append((key, pal, bloom, ncc, ncn, nss, npsl, nwm))

# rooms with SuperStructureProjector (the glyph projection) = the iterator "brain" rooms
print("=== rooms WITH SuperStructureProjector (glyph projection active) ===")
print("room        pal  bloom  Circuit Neuron Proj ScanLines Mycelia")
for r in rows:
    if r[5] > 0:
        print("%-11s %3d  %.3f  %5d %6d %4d %8d %7d" % r)

print()
print("=== top rooms by CoralCircuit count ===")
for r in sorted(rows, key=lambda x: -x[3])[:10]:
    print("%-11s pal=%3d bloom=%.3f circuit=%d neuron=%d proj=%d" % (r[0], r[1], r[2], r[3], r[4], r[5]))
