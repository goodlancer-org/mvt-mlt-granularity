"""Render three nested Standard MVT tiles for every final archive, without plot text.

Run via ``python manage.py maps``. No analysis database, server or network required.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import yaml
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mapbox_vector_tile
from pmtiles.reader import Reader
from pmtiles.tile import tileid_to_zxy, zxy_to_tileid
from shapely.affinity import scale
from shapely.geometry import shape

from . import output_analysis_core as core
from .map_styles.drawing import draw

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "app/data/output"
DEFAULT_OUTPUT = ROOT / "outputs/figures"
DEFAULT_REGIONS = Path(__file__).with_name("map_regions.yaml")
MODULES = ("ne_fig", "nl_fig", "nwi_fig", "swiss_fig", "osm_fig")
DETAILS = {
    "natural_earth_vector": (
        "Natural Earth", "New York / New Jersey",
        "Colors are illustrative: blue water, pale land, tan urban areas, green parks, "
        "red/orange/yellow roads, purple state boundaries and gray county boundaries. "
        "Points mark places and transport facilities. Source: Natural Earth / NACIS."),
    "pdok_netherlands_infrostructure": (
        "PDOK BGT", "Nijmegen, Netherlands",
        "The palette follows the BGT standard visualization: red buildings, blue water, "
        "green vegetation and white local roads/paved areas; gray denotes classes without "
        "an assigned standard color. Source: PDOK."),
    "usfws_luisiana_wetlands_geopackage": (
        "USFWS wetlands", "coastal Louisiana",
        "The NWI palette distinguishes forested/shrub wetlands (dark green), emergent wetlands "
        "(light green), tidal wetlands (teal), and water classes (blue); unclassified polygons "
        "are light gray. Source: U.S. Fish and Wildlife Service, National Wetlands Inventory."),
    "swisstopo_mountains_vector": (
        "swisstopo geology", r"S\"antis, Switzerland",
        "Colors distinguish geological units using the swisstopo legend and the retained "
        r"\texttt{SYMBOL}/\texttt{INDEX\_} attributes. White denotes units without an assigned "
        "legend color. Source: swisstopo, Structural Map of the Helvetic Zone, sheet 128."),
    "louisiana-260912": (
        "OpenStreetMap", "coastal Louisiana",
        "An illustrative tag-based palette shows water in blue, wetlands in teal, vegetation "
        "in green, buildings in brown, roads/routes in orange and other objects in gray. "
        "Classification uses retained OSM tags rather than merged tile-layer names. "
        r"Source: \copyright{} OpenStreetMap contributors, ODbL."),
}


def tex(value):
    return ''.join({'\\': r'\textbackslash{}', '_': r'\_', '&': r'\&', '%': r'\%',
                    '#': r'\#', '$': r'\$', '{': r'\{', '}': r'\}'}.get(c, c) for c in str(value))


def discover(directory):
    """The exact final suffix excludes dense, MLT and converter scratch files."""
    paths = sorted(Path(directory).glob("*_standard_mvt.pmtiles"))
    if not paths:
        raise RuntimeError(f"No final Standard MVT archives in {directory}")
    return paths


def read_tile(reader, address):
    payload = reader.get(*address)
    if payload is None:
        raise RuntimeError(f"Missing tile {address}")
    compression = reader.header()['tile_compression']
    payload = core._decompress(payload, compression.value, str(address))
    decoded = mapbox_vector_tile.decode(payload, default_options={'y_coord_down': True})
    layers = {}
    for name, layer in decoded.items():
        extent = layer['extent']
        if extent <= 0:
            raise RuntimeError(f"Invalid extent in {address}/{name}: {extent}")
        features = [(shape(f['geometry']), f['properties']) for f in layer['features']]
        layers[name] = features if extent == 4096 else [
            (scale(g, xfact=4096/extent, yfact=4096/extent, origin=(0, 0)), p) for g, p in features]
    if not any(layers.values()):
        raise RuntimeError(f"Empty tile {address}")
    return layers


def automatic_tiles(path, reader):
    """Choose nonempty nested tiles near the archive center, without decoding all data."""
    h = reader.header()
    metadata = reader.metadata()
    min_z = max(h['min_zoom'], min((l.get('minzoom', h['min_zoom'])
                                  for l in metadata.get('vector_layers', [])), default=h['min_zoom']))
    max_z = h['max_zoom']
    if max_z-min_z < 2:
        raise RuntimeError(f"{path.name}: three distinct zoom levels are unavailable")
    zooms = sorted({max(min_z, max_z-4), max(min_z+1, max_z-2), max_z})
    lon, lat = h['center_lon_e7']/1e7, h['center_lat_e7']/1e7
    lat = max(-85.051128, min(85.051128, lat))
    x = max(0, min(2**max_z-1, int((lon+180)/360 * 2**max_z)))
    y = max(0, min(2**max_z-1, int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2 * 2**max_z)))
    target = zxy_to_tileid(max_z, x, y)
    low, high = zxy_to_tileid(max_z, 0, 0), (4**(max_z+1)-1)//3
    candidates = set()
    for entry in core.iter_tile_runs(path):
        start, stop = max(low, entry.tile_id), min(high, entry.tile_id+entry.run_length)
        if start < stop:
            for tile_id in (start, stop-1, max(start, min(stop-1, target))):
                candidates.add(tileid_to_zxy(tile_id))
    for _, xx, yy in sorted(candidates, key=lambda t: ((t[1]-x)**2+(t[2]-y)**2, t)):
        addresses = [(z, xx >> (max_z-z), yy >> (max_z-z)) for z in zooms]
        try:
            for address in addresses:
                read_tile(reader, address)
        except RuntimeError:
            continue
        return addresses
    raise RuntimeError(f"{path.name}: no nonempty nested three-zoom sample found; configure tiles explicitly")


def world_xy(lon, lat):
    """Normalized Web Mercator (top-left origin)."""
    return (lon+180)/360, (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2


def view_in_tile(address, bounds):
    z, x, y = address
    w, south, e, north = bounds
    left, top = world_xy(w, north)
    right, bottom = world_xy(e, south)
    return [(left*2**z-x)*4096, (top*2**z-y)*4096,
            (right*2**z-x)*4096, (bottom*2**z-y)*4096]


def load_regions(path=DEFAULT_REGIONS):
    config = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if not isinstance(config, dict) or config.get('version') != 1 or not isinstance(config.get('datasets'), dict):
        raise RuntimeError(f'{path}: expected version: 1 and a datasets mapping')
    for stem, region in config['datasets'].items():
        panels = region.get('panels', [])
        if len(panels) != 3:
            raise RuntimeError(f'{stem}: configure exactly three panels')
        for panel in panels:
            z, x, y = (panel.get(k) for k in ('z', 'x', 'y'))
            if any(type(v) is not int for v in (z,x,y)) or not (0 <= z <= 30 and 0 <= x < 2**z and 0 <= y < 2**z):
                raise RuntimeError(f'{stem}: invalid tile address {panel}')
            for key in ('view_bounds', 'level_bounds'):
                b = panel.get(key)
                if not isinstance(b, list) or len(b) != 4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in b):
                    raise RuntimeError(f'{stem}: {key} must contain four finite coordinates')
                if not (-180 <= b[0] < b[2] <= 180 and -85.051129 <= b[1] < b[3] <= 85.051129):
                    raise RuntimeError(f'{stem}: invalid {key}: {b}')
            v, b = panel['view_bounds'], panel['level_bounds']
            if v[0] < b[0]-1e-8 or v[1] < b[1]-1e-8 or v[2] > b[2]+1e-8 or v[3] > b[3]+1e-8:
                raise RuntimeError(f'{stem}: viewport exceeds its zoom-level bounds')
            l,t,r,bot = view_in_tile((z,x,y),v)
            if min(l,t) < -1e-5 or max(r,bot) > 4096+1e-5 or abs((r-l)-(bot-t)) > 1e-5:
                raise RuntimeError(f'{stem}: viewport must be square in Web Mercator and inside its tile')
        for parent, child in zip(panels,panels[1:]):
            z,x,y = (parent[k] for k in ('z','x','y'))
            zz,xx,yy = (child[k] for k in ('z','x','y'))
            if zz <= z or (xx >> (zz-z), yy >> (zz-z)) != (x,y):
                raise RuntimeError(f'{stem}: tile addresses must be nested in increasing zoom order')
            b,v = parent['view_bounds'],child['view_bounds']
            if v[0] < b[0]-1e-8 or v[1] < b[1]-1e-8 or v[2] > b[2]+1e-8 or v[3] > b[3]+1e-8:
                raise RuntimeError(f'{stem}: child viewport exceeds parent viewport')
    return config['datasets']


def config_for(stem):
    for name in MODULES:
        cfg = importlib.import_module('.map_styles.'+name, __package__).cfg
        if cfg['stem'] == stem:
            return dict(cfg)
    palette = json.loads(Path(__file__).with_name('style.json').read_text(encoding='utf-8'))
    return dict(stem=stem, zorder=list(palette),
                cls=lambda layer, props: layer,
                style=lambda layer, props: (palette.get(layer, palette['default']), '#535353', None, False, 'layer palette'))


def tile_side_km(z, y):
    lat = math.atan(math.sinh(math.pi*(1-2*(y+.5)/2**z)))
    return 2*math.pi*6378.137*math.cos(lat)/2**z


def view_side_km(bounds):
    left, top = world_xy(bounds[0], bounds[3])
    right, bottom = world_xy(bounds[2], bounds[1])
    lat = math.atan(math.sinh(math.pi*(1-top-bottom)))
    return 2*math.pi*6378.137*math.cos(lat)*(right-left)


def render_dataset(path, output, dpi, regions):
    stem = path.name.removesuffix('_standard_mvt.pmtiles')
    cfg = config_for(stem)
    records, inventory = [], Counter()
    with path.open('rb') as handle:
        def get_bytes(offset, length):
            handle.seek(offset)
            return handle.read(length)
        reader = Reader(get_bytes)
        selected = regions.get(stem)
        panels = selected['panels'] if selected else None
        addresses = [(p['z'], p['x'], p['y']) for p in panels] if panels else automatic_tiles(path, reader)
        if len(addresses) != 3 or len({t[0] for t in addresses}) != 3:
            raise RuntimeError(f'{stem}: expected three distinct zoom levels')
        for parent, child in zip(addresses, addresses[1:]):
            z, x, y = parent
            zz, xx, yy = child
            if zz <= z or (xx >> (zz-z), yy >> (zz-z)) != (x, y):
                raise RuntimeError(f'{stem}: tiles are not nested: {parent}, {child}')
        for z, x, y in addresses:
            print(f"  {stem}: {z}/{x}/{y}", flush=True)
            layers = read_tile(reader, (z, x, y))
            fig = plt.figure(figsize=(2.25, 2.25), facecolor='white')
            ax = fig.add_axes([0, 0, 1, 1])
            draw(ax, layers, cfg)
            panel = panels[len(records)] if panels else None
            if panel:
                h = reader.header()
                archive_bounds = [h[k]/1e7 for k in ('min_lon_e7','min_lat_e7','max_lon_e7','max_lat_e7')]
                v = panel['view_bounds']
                if any((v[0] < archive_bounds[0]-1e-8, v[1] < archive_bounds[1]-1e-8,
                        v[2] > archive_bounds[2]+1e-8, v[3] > archive_bounds[3]+1e-8)):
                    raise RuntimeError(f'{stem}: configured viewport exceeds current archive bounds')
                left,top,right,bottom = view_in_tile((z,x,y),v)
                ax.set_xlim(left,right); ax.set_ylim(bottom,top)
            for artist in ax.collections:
                artist.set_rasterized(True)
            # Visual locator only: outlines show the exact footprint of the next panel.
            child = addresses[len(records)+1] if len(records)+1 < len(addresses) else None
            if child:
                from matplotlib.patches import Rectangle
                zz, xx, yy = child
                factor = 2**(zz-z)
                if panels:
                    l,t,r,b = view_in_tile((z,x,y),panels[len(records)+1]['view_bounds'])
                else:
                    l,t = (xx-x*factor)*4096/factor, (yy-y*factor)*4096/factor
                    r,b = l+4096/factor,t+4096/factor
                ax.add_patch(Rectangle((l,t),r-l,b-t,fill=False,ec='#e6007e',lw=.9,zorder=100))
            filename = f'map_{stem}_z{z}'
            for suffix in ('png', 'pdf'):
                fig.savefig(output/(filename+'.'+suffix), dpi=dpi, facecolor='white', pad_inches=0)
            plt.close(fig)
            counts = {name: len(features) for name, features in layers.items()}
            for layer, features in layers.items():
                for geom, props in features:
                    fc, ec, hatch, official, source = cfg['style'](layer, props)
                    category = str(cfg['cls'](layer, props))
                    inventory[(layer, category, fc, ec, hatch, source)] += 1
            records.append(dict(z=z, x=x, y=y, side_km=tile_side_km(z,y), features=counts,
                                image=filename, extents_normalized_to=4096,
                                tile_side_km=tile_side_km(z,y),
                                view_side_km=view_side_km(panel['view_bounds']) if panel else tile_side_km(z,y),
                                view_bounds=panel['view_bounds'] if panel else None,
                                level_bounds=panel['level_bounds'] if panel else None))
    with path.open('rb') as handle:
        archive_hash = hashlib.file_digest(handle, 'sha256').hexdigest()
    return dict(dataset=stem, archive=path.name, archive_sha256=archive_hash,
                region=selected.get('region') if selected else None,
                panels=records, color_key=[dict(layer=k[0], category=k[1], fill=k[2], outline=k[3],
                    pattern=k[4], source=k[5], features=n) for k,n in sorted(inventory.items(), key=lambda kv: (kv[0][0],kv[0][1]))])


def write_latex(records, output):
    """One page: five rows, three map views and a LaTeX description per row."""
    lines = ['% Generated by python manage.py maps; text stays in LaTeX.',
             r'\begin{figure*}[p]', r'\centering', r'\begingroup',
             r'\setlength{\tabcolsep}{2pt}', r'\renewcommand{\arraystretch}{1}',
             r'\begin{tabular}{@{}cccc@{}}']
    for index, record in enumerate(records):
        stem = record['dataset']
        name, region, explanation = DETAILS.get(stem, (tex(stem), 'archive study area',
            'Colors distinguish retained tile layers using the common analysis palette.'))
        if record.get('region'):
            region = tex(record['region'])
        cells = []
        for panel in record['panels']:
            cells.append(r'\begin{minipage}[t]{0.205\textwidth}\vspace{0pt}\centering'
                         r'\includegraphics[width=\linewidth]{figures/'+panel['image']+'.pdf}'
                         r'\par\vspace{1pt}\scriptsize $z='+str(panel['z'])+r'$\end{minipage}')
        cells.append(r'\begin{minipage}[t]{0.34\textwidth}\vspace{1pt}\footnotesize\raggedright '
                     r'\textbf{('+chr(97+index)+') '+name+r'}\\ '+region+r'.\par\smallskip '+explanation+r'\end{minipage}')
        lines.append(' & '.join(cells)+r' \\[5pt]')
    lines += [r'\end{tabular}',r'\endgroup',
              r'\caption{The five datasets at three zoom levels, rendered from Standard MVT tiles. '
              'Views are nested from left to right; magenta outlines locate the next view. '
              'Square viewports stay within the configured data bounds at each zoom. '
              'USFWS and OSM show the same coastal Louisiana areas.}',r'\label{fig:datasets}']
    for record in records:
        lines.append(r'\label{fig:map-'+record['dataset']+'}')
    lines.append(r'\end{figure*}')
    (output/'map_samples.tex').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def write_color_key(records, output):
    lines = ['# Displayed map color keys', '',
             'Generated by `python manage.py maps`. Counts sum features over the three displayed tiles; '
             'a feature can occur at several zooms. These colors are for visualization, not a format comparison.', '']
    for record in records:
        lines += ['## '+record['dataset'], '',
                  'Tiles: '+', '.join(f"`{p['z']}/{p['x']}/{p['y']}`" for p in record['panels']), '',
                  '| Layer | Class/value | Fill | Outline | Pattern | Source | Features |',
                  '|---|---|---|---|---|---|---:|']
        for row in record['color_key']:
            values = [row[key] for key in ('layer','category','fill','outline','pattern','source','features')]
            lines.append('| '+' | '.join(str(v).replace('|', '&#124;') if v is not None else '--' for v in values)+' |')
        lines.append('')
    (output/'map_samples_color_key.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def generate(input_dir=DEFAULT_INPUT, output_dir=DEFAULT_OUTPUT, dpi=450, regions_file=DEFAULT_REGIONS):
    paths = discover(input_dir)
    regions = load_regions(regions_file)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    # Match corpus order; automatically append new final Standard archives.
    paths.sort(key=lambda p: (list(DETAILS).index(p.name.removesuffix('_standard_mvt.pmtiles'))
                              if p.name.removesuffix('_standard_mvt.pmtiles') in DETAILS else len(DETAILS), p.name))
    records = [render_dataset(path, output, dpi, regions) for path in paths]
    write_latex(records, output)
    manifest = dict(format='MVT', variant='standard', dpi=dpi,
                    regions_file=str(Path(regions_file).resolve()),
                    regions_sha256=hashlib.sha256(Path(regions_file).read_bytes()).hexdigest(), datasets=records)
    (output/'map_samples.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    write_color_key(records, output)
    print(f"Generated {len(records)} maps ({sum(len(r['panels']) for r in records)} panels): {output}", flush=True)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--dpi', type=int, default=450)
    parser.add_argument('--regions', type=Path, default=DEFAULT_REGIONS)
    args = parser.parse_args()
    if args.dpi <= 0:
        parser.error('--dpi must be positive')
    generate(args.input_dir, args.output_dir, args.dpi, args.regions)


if __name__ == '__main__':
    main()
