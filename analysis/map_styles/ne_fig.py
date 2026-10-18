"""Natural Earth illustrative class palette.
Natural Earth has no official vector style."""
from .drawing import W, G
C = dict(ocean='#b9d7ee', lake='#8fc1e6', river='#5b9bd5', land='#f3efe4', urban='#e2cfb4', park='#cfe5c3', park_e='#9cc58a', coast='#4f7fa6', b0='#222222', b1='#8e5ea2', b2='#b5b5b5', fwy='#d94f30', pri='#f0a030', sec='#f4d03f', road='#b9ad96', rail='#555555', ferry='#7e57c2', port='#1f4e79', air='#2e7d32', place='#7a1f1f', cap0='#000000', cap1='#444444')
FALLBACK = '#9a9a9a'

def cls(layer, p):
    fc = p.get('featurecla') or p.get('FEATURECLA')
    if layer == 'transportation':
        return fc if fc in ('Port', 'Airport', 'Railroad') else p.get('type') or p.get('TYPE') or fc
    return fc
T = {('hydrography', 'Ocean'): (C['ocean'], C['ocean'], None, 0), ('hydrography', 'Lake'): (C['lake'], C['lake'], None, 2), ('hydrography', 'Reservoir'): (C['lake'], C['lake'], None, 2), ('hydrography', 'River'): (None, C['river'], 'line:.7', 4.5), ('hydrography', 'Lake Centerline'): (None, C['river'], 'line:.5', 4.5), ('land_use', 'Land'): (C['land'], C['land'], None, 1), ('land_use', 'Urban area'): (C['urban'], C['urban'], None, 3), ('land_use', 'National Park Service'): (C['park'], C['park_e'], None, 3), ('land_use', 'Coastline'): (None, C['coast'], 'line:.7', 4), ('land_use', 'Minor coastline'): (None, C['coast'], 'line:.4', 4), ('transportation', 'Other Paved'): (None, C['road'], 'line:.4', 8), ('transportation', 'Road'): (None, C['road'], 'line:.5', 8.1), ('transportation', 'Secondary'): (None, C['sec'], 'line:.7', 8.2), ('transportation', 'Secondary Highway'): (None, C['sec'], 'line:.7', 8.2), ('transportation', 'Primary'): (None, C['pri'], 'line:.9', 8.3), ('transportation', 'Bypass'): (None, C['pri'], 'line:.9', 8.3), ('transportation', 'Freeway'): (None, C['fwy'], 'line:1.1', 8.4), ('transportation', 'Tollway'): (None, C['fwy'], 'line:1.1', 8.4), ('transportation', 'Major Highway'): (None, C['fwy'], 'line:1.1', 8.4), ('transportation', 'Beltway'): (None, C['fwy'], 'line:1.1', 8.4), ('transportation', 'Railroad'): (None, C['rail'], 'line:.6', 8.5), ('transportation', 'Ferry'): (None, C['ferry'], 'line:.6', 8.6), ('transportation', 'Ferry Route'): (None, C['ferry'], 'line:.6', 8.6), ('transportation', 'Port'): (None, C['port'], 'pt', 9), ('transportation', 'Airport'): (None, C['air'], 'pt', 9), ('places', 'Populated place'): (None, C['place'], 'pt', 10), ('places', 'Admin-0 capital'): (None, C['cap0'], 'pt', 10), ('places', 'Admin-1 capital'): (None, C['cap1'], 'pt', 10), ('places', 'Timezone'): (None, '#d8d8d8', 'line:.3', 0.5)}
PREFIX_LAYERS = ('boundaries', 'places')
PREFIX = [('Admin-0', C['b0'], 0.8, 7), ('Admin-1', C['b1'], 0.6, 6), ('Admin-2', C['b2'], 0.3, 5)]

def _lookup(layer, v):
    if (layer, v) in T:
        return T[layer, v]
    if v and layer in PREFIX_LAYERS:
        for pre, col, w, z in PREFIX:
            if v.startswith(pre):
                return (None, col, f'line:{w}', z)
    return None

def style(layer, p):
    t = _lookup(layer, cls(layer, p))
    if t:
        return (t[0], t[1], t[2], True, 'convention')
    return (None, FALLBACK, 'line:.3', False, '')

def zfun(layer, p):
    t = _lookup(layer, cls(layer, p))
    return t[3] if t else 0.7
cfg = dict(stem='natural_earth_vector', zorder=['land_use', 'hydrography', 'boundaries', 'transportation', 'places'], zfun=zfun, style=style, cls=cls, pt_s=3)
