"""Style OSM by retained tags rather than misleading merged layer names."""
import re
COLORS = {'Water': '#8fc1e6', 'Wetland': '#80bfa8', 'Vegetation': '#c5dca5', 'Buildings': '#d3a28c', 'Roads and routes': '#cc8b49', 'Other': '#8c8c8c'}

def tags(props):
    extra = dict(re.findall('"((?:[^"\\\\]|\\\\.)*)"=>"((?:[^"\\\\]|\\\\.)*)"', str(props.get('other_tags', ''))))
    return {**extra, **{k: v for k, v in props.items() if v is not None}}

def category(layer, props):
    p = tags(props)
    if p.get('natural') in ('water', 'bay') or p.get('waterway') or p.get('water'):
        return 'Water'
    if p.get('natural') == 'wetland':
        return 'Wetland'
    if p.get('building') and p['building'] != 'no':
        return 'Buildings'
    if p.get('highway') or p.get('railway') or p.get('route') or (layer == 'transportation'):
        return 'Roads and routes'
    if p.get('landuse') or p.get('natural') in ('wood', 'scrub', 'grassland', 'heath') or p.get('leisure') == 'park':
        return 'Vegetation'
    return 'Other'

def style(layer, props):
    c = COLORS[category(layer, props)]
    return (c, c, None, False, 'illustrative OSM tag palette')
cfg = dict(stem='louisiana-260912', zorder=['buildings', 'transportation'], style=style, cls=category, zfun=lambda l, p: list(COLORS).index(category(l, p)), poly_lw=0.15, pt_s=1)
