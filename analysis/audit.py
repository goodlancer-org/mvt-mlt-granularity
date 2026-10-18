"""Local bounds provenance and full decoded MVT/MLT validation (P0.4)."""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import inspect
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import os
import uuid
import subprocess
import sys
from pathlib import Path
import sqlite3
import time

import mapbox_vector_tile
import maplibre_tiles
import numpy as np
import pyogrio
from pyproj import Transformer
from shapely import from_wkb, normalize, to_wkb
from shapely.geometry import shape
import yaml

from . import output_analysis_core as core

VARIANTS = {'standard': (4096, 0), 'dense4': (8192, 1), 'dense16': (16384, 2)}


def union(bounds):
    bounds = [b for b in bounds if b is not None]
    return [min(b[0] for b in bounds), min(b[1] for b in bounds),
            max(b[2] for b in bounds), max(b[3] for b in bounds)] if bounds else None


def finite_bounds(value):
    return (value is not None and len(value) == 4 and all(math.isfinite(float(v)) for v in value)
            and value[0] <= value[2] and value[1] <= value[3])


def typed_value(value):
    # Unlike the legacy converter validator, do not stringify property values:
    # True, 1 and "1" are distinct. Nulls and non-finite numbers are explicit.
    if value is None:
        return ('null', '')
    if isinstance(value, bool):
        return ('bool', str(value))
    if isinstance(value, int):
        return ('int', str(value))
    if isinstance(value, float):
        return ('float', value.hex())
    if isinstance(value, str):
        return ('str', value)
    raise TypeError(f'Unsupported property type: {type(value).__name__}')


def feature_key(identifier, properties, geometry):
    # Feature order and ring starting vertices/orientation are not semantic.
    # normalize preserves vertices, geometry types, parts and duplicate features.
    # Omitted protobuf feature IDs have default zero, as in the converter validator.
    return (int(identifier or 0), tuple(sorted((str(k), typed_value(v)) for k, v in properties.items())),
            to_wkb(normalize(geometry), byte_order=1, output_dimension=2))


def decoded_tile(raw, fmt):
    """Canonical feature multisets and local geometry bounds per named layer."""
    content, extents, bounds, counts = {}, {}, {}, {}
    if fmt == 'MVT':
        decoded = mapbox_vector_tile.decode(raw, default_options={'y_coord_down': True})
        layers = ((name, layer['extent'],
                   ((f.get('id'), f.get('properties') or {}, shape(f['geometry'])) for f in layer['features']))
                  for name, layer in decoded.items())
    else:
        layers = ((layer.name, layer.extent,
                   ((f.id, dict(f.properties), from_wkb(f.wkb)) for f in layer.features))
                  for layer in maplibre_tiles.decode_mlt(raw))
    for name, extent, features in layers:
        if name in content:
            raise ValueError(f'Duplicate layer name: {name}')
        histogram, boxes = Counter(), []
        for identifier, properties, geometry in features:
            histogram[feature_key(identifier, properties, geometry)] += 1
            if not geometry.is_empty:
                boxes.append(geometry.bounds)
        content[str(name)] = histogram
        extents[str(name)] = int(extent)
        bounds[str(name)] = union(boxes)
        counts[str(name)] = sum(histogram.values())
    return content, extents, bounds, counts


def polygon_rings(commands):
    """Read every wire ring, including zero-area rings skipped by the GeoJSON decoder."""
    rings, ring = [], []
    x = y = i = 0
    while i < len(commands):
        command = commands[i]; i += 1
        kind, count = command & 7, command >> 3
        if not count: raise ValueError('Zero-length geometry command')
        if kind in (1, 2):
            if kind == 1 and ring:
                rings.append(ring if ring[0] == ring[-1] else ring+[ring[0]])
                ring = []
            for _ in range(count):
                a,b = commands[i:i+2]; i += 2
                x += (a>>1) ^ -(a&1); y += (b>>1) ^ -(b&1)
                ring.append((x,y))
        elif kind == 7:
            if count != 1 or not ring: raise ValueError('Invalid polygon ClosePath')
            rings.append(ring if ring[0] == ring[-1] else ring+[ring[0]])
            ring = []
        else: raise ValueError(f'Invalid polygon command: {kind}')
    if ring: rings.append(ring if ring[0] == ring[-1] else ring+[ring[0]])
    return rings


@lru_cache(maxsize=2)
def polygon_wire_signature(raw, fmt):
    """Diagnostic only: compare polygon rings/attributes without assuming ring grouping.

    Matching this signature NEVER overrides a decoded topology mismatch.
    """
    from mapbox_vector_tile.Mapbox.vector_tile_pb2 import tile as Tile
    from mapbox_vector_tile.decoder import TileData
    from shapely.geometry import Polygon

    def rings_key(rings):
        values=[]
        for ring in rings:
            area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]))
            values.append((int(area>0)-int(area<0),to_wkb(normalize(Polygon(ring)),byte_order=1)))
        return tuple(sorted(values))
    out={}
    if fmt == 'MVT':
        tile=Tile();tile.ParseFromString(raw)
        for layer in tile.layers:
            values=Counter()
            for feature in layer.features:
                if feature.type != 3: continue
                properties={layer.keys[k]:TileData.parse_value(layer.values[v]) for k,v in zip(feature.tags[::2],feature.tags[1::2])}
                key=(int(feature.id),tuple(sorted((k,typed_value(v)) for k,v in properties.items())),rings_key(polygon_rings(feature.geometry)))
                values[key]+=1
            out[layer.name]=values
    else:
        for layer in maplibre_tiles.decode_mlt(raw):
            values=Counter()
            for feature in layer.features:
                geom=from_wkb(feature.wkb)
                if geom.geom_type not in ('Polygon','MultiPolygon'): continue
                polygons=[geom] if geom.geom_type=='Polygon' else geom.geoms
                rings=[list(r.coords) for p in polygons for r in [p.exterior,*p.interiors]]
                key=(int(feature.id or 0),tuple(sorted((k,typed_value(v)) for k,v in feature.properties.items())),rings_key(rings))
                values[key]+=1
            out[layer.name]=values
    return out


def tile_bounds(z, x, y, local=None, extent=1):
    """Tile-local coordinates are x-right/y-down in both independent decoders."""
    a, b, c, d = local if local is not None else (0, 0, 1, 1)
    n = 2 ** z
    def lon(px): return (x + px / extent) / n * 360 - 180
    def lat(py): return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + py / extent) / n))))
    return [lon(a), lat(d), lon(c), lat(b)]


class Audit:
    def __init__(self, target, root, data, datasets):
        self.root, self.data, self.datasets = Path(root), Path(data), datasets
        self.con = sqlite3.connect(target)
        self.hashes = {}
        self.issue_counts = defaultdict(int)
        self.source_bounds, self.normalized_bounds, self.configured = {}, {}, {}
        self.con.executescript('''
          CREATE TABLE bounds(id INTEGER PRIMARY KEY,dataset_id TEXT,stage TEXT,variant TEXT,
            format TEXT,kind TEXT,component TEXT,layer_name TEXT,zoom INTEGER,
            min_lon REAL,min_lat REAL,max_lon REAL,max_lat REAL,native_crs TEXT,
            native_bounds_json TEXT,path TEXT,sha256 TEXT,method TEXT,status TEXT,details_json TEXT);
          CREATE TABLE bounds_checks(dataset_id TEXT,variant TEXT,format TEXT,zoom INTEGER,
            check_name TEXT,status TEXT,tolerance_degrees REAL,west_excess REAL,south_excess REAL,
            east_excess REAL,north_excess REAL,message TEXT);
          CREATE TABLE validation(dataset_id TEXT,variant TEXT,mode TEXT,mvt_path TEXT,mlt_path TEXT,
            mvt_sha256 TEXT,mlt_sha256 TEXT,mvt_tiles INTEGER,mlt_tiles INTEGER,checked_tiles INTEGER,
            mismatches INTEGER,errors INTEGER,missing_mvt INTEGER,missing_mlt INTEGER,
            passed INTEGER,status TEXT,elapsed_seconds REAL,validated_at_utc TEXT,
            PRIMARY KEY(dataset_id,variant));
          CREATE TABLE validation_issues(dataset_id TEXT,variant TEXT,z INTEGER,x INTEGER,y INTEGER,
            category TEXT,layer_name TEXT,details_json TEXT);
        ''')

    def digest(self, path):
        path = Path(path)
        if path not in self.hashes:
            h = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(8*1024*1024), b''): h.update(block)
            self.hashes[path] = h.hexdigest()
        return self.hashes[path]

    def relative(self, path):
        try: return Path(path).relative_to(self.root).as_posix()
        except ValueError: return str(path)

    def record(self, dataset, stage, kind, box, path, method, *, variant=None, fmt=None,
               component=None, layer=None, zoom=None, native_crs=None, native=None,
               status=None, details=None):
        if not finite_bounds(box): box = None
        self.con.execute('INSERT INTO bounds VALUES (NULL,' + ','.join('?'*19) + ')',
            (dataset, stage, variant, fmt, kind, component, layer, zoom,
             *(box or [None]*4), native_crs, json.dumps(native), self.relative(path),
             self.digest(path), method, status or ('measured' if box else 'unknown'), json.dumps(details or {})))

    def containment(self, dataset, name, observed, reference, tolerance=1e-5, *, variant=None, fmt=None, zoom=None):
        excess = ([max(0, reference[0]-observed[0]), max(0, reference[1]-observed[1]),
                   max(0, observed[2]-reference[2]), max(0, observed[3]-reference[3])]
                  if finite_bounds(observed) and finite_bounds(reference) else None)
        status = 'unknown' if excess is None else ('pass' if max(excess) <= tolerance else 'fail')
        self.con.execute('INSERT INTO bounds_checks VALUES (' + ','.join('?'*12) + ')',
            (dataset, variant, fmt, zoom, name, status, tolerance, *(excess or [None]*4),
             'WGS84 bounding-box containment; missing bounds are not inferred'))

    def vector_bounds(self, dataset, stage, path):
        from .map_analysis_core import _materialize_components
        all_boxes, complete = [], True
        for component in _materialize_components(path, self.data/'.analysis_cache'):
            print(f'Bounds {stage}: {dataset} / {component.name}', flush=True)
            try:
                layers = pyogrio.list_layers(component)
            except Exception as error:
                complete = False
                self.record(dataset, stage, 'geometry', None, path, 'OGR geometry envelopes',
                            component=component.name, details={'error': str(error)})
                continue
            for name, kind in layers:
                if not kind: continue
                native = box = None
                crs = None
                details = {}
                try:
                    info = pyogrio.read_info(component, layer=name)
                    crs = info.get('crs')
                    _, envelopes = pyogrio.read_bounds(component, layer=name)
                    valid = np.isfinite(envelopes).all(axis=0)
                    if valid.any():
                        e = envelopes[:, valid]
                        native = [float(e[0].min()), float(e[1].min()), float(e[2].max()), float(e[3].max())]
                        if not crs: raise ValueError('Missing CRS; native bounds retained, WGS84 unknown')
                        box = list(Transformer.from_crs(crs, 4326, always_xy=True).transform_bounds(*native, densify_pts=21))
                    details = {'features_with_finite_envelopes': int(valid.sum()), 'features_without_finite_envelopes': int((~valid).sum())}
                except Exception as error:
                    complete = False
                    details['error'] = f'{type(error).__name__}: {error}'
                self.record(dataset, stage, 'geometry', box, path, 'OGR read_bounds over feature geometry; transformed envelope (21-point edge densification)',
                            component=component.name, layer=str(name), native_crs=str(crs) if crs else None, native=native, details=details)
                all_boxes.append(box)
        total = union(all_boxes)
        self.record(dataset, stage, 'geometry', total, path, 'union of measured layer envelopes',
                    status=('measured' if complete else 'partial') if total else 'unknown', details={'complete': complete})
        return total if complete else None

    def configuration(self, d):
        # Use the converter's own matching implementation, without importing its CLI.
        from app.converter.src.profile_rules import _select_dataset_rule
        rules_path = self.root/'app/converter/profiles/profile_rules.yaml'
        profile_path = self.root/d['profile']
        rules = yaml.safe_load(rules_path.read_text(encoding='utf-8')) if rules_path.exists() else {}
        rule = _select_dataset_rule(rules, dataset_name=d['id'], source_path=d['source'], source_format=Path(d['source']).suffix.lstrip('.'))
        rule_box = ((rule or {}).get('output') or {}).get('bounds')
        profile = yaml.safe_load(profile_path.read_text(encoding='utf-8'))
        profile_box = (profile.get('output') or {}).get('bounds')
        if rules_path.exists():
            self.record(d['id'], 'configuration', 'rule', rule_box, rules_path, 'converter dataset-rule matching',
                        details={'rule_name': (rule or {}).get('name'), 'historical_run_proven': False})
        self.record(d['id'], 'configuration', 'profile', profile_box, profile_path, 'generated profile output.bounds',
                    details={'historical_run_proven': False})
        manifest_path = (self.root/d['normalized']).with_suffix('.normalization.json')
        manifest_box = None
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest_box = manifest.get('bounds')
            if manifest_box: manifest_box = [float(v) for v in manifest_box]
            self.record(d['id'], 'configuration', 'normalization_manifest', manifest_box, manifest_path,
                        'persisted normalization manifest bounds', details={'clip_to_bounds': manifest.get('clip_to_bounds')})
        else:
            self.record(d['id'], 'configuration', 'normalization_manifest', None, self.root/d['normalized'],
                        'normalization manifest absent', details={'expected_path': self.relative(manifest_path), 'historical_run_proven': False})
        if rule_box is not None and profile_box is not None:
            delta = max(abs(a-b) for a, b in zip(rule_box, profile_box))
            self.con.execute('INSERT INTO bounds_checks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (d['id'], None, None, None, 'rule_matches_profile', 'pass' if delta <= 1e-10 else 'fail', 1e-10, None, None, None, None, f'maximum coordinate difference: {delta}'))
        # Current settings are references, never asserted to be historical run settings.
        return profile_box or rule_box or manifest_box

    def sources_and_normalized(self):
        for d in self.datasets:
            self.configured[d['id']] = self.configuration(d)
            self.source_bounds[d['id']] = self.vector_bounds(d['id'], 'source', self.root/d['source'])
            self.normalized_bounds[d['id']] = self.vector_bounds(d['id'], 'normalized', self.root/d['normalized'])
            self.containment(d['id'], 'normalized_within_source', self.normalized_bounds[d['id']], self.source_bounds[d['id']])
            self.containment(d['id'], 'normalized_within_current_config', self.normalized_bounds[d['id']], self.configured[d['id']])
            self.con.commit()

    def source_cache_key(self):
        paths=[self.root/d[k] for d in self.datasets for k in ('source','normalized','profile')]
        paths += [self.root/'app/converter/profiles/profile_rules.yaml']
        paths += [(self.root/d['normalized']).with_suffix('.normalization.json') for d in self.datasets]
        paths += [Path(__file__).parent/'map_analysis_core.py',self.root/'app/converter/src/profile_rules.py']
        facts=[(self.relative(p),self.digest(p) if p.exists() else None) for p in paths]
        methods=[Audit.vector_bounds,Audit.configuration,Audit.sources_and_normalized,Audit.record,Audit.containment,union,finite_bounds]
        code='\n'.join(inspect.getsource(f) for f in methods)
        from importlib.metadata import version
        versions={p:version(p) for p in ('pyogrio','pyproj','numpy')}
        return hashlib.sha256(json.dumps([facts,code,versions],sort_keys=True).encode()).hexdigest()

    def restore_source_references(self):
        for d in self.datasets:
            dataset=d['id']
            for stage, dest in [('source',self.source_bounds),('normalized',self.normalized_bounds)]:
                row=self.con.execute("SELECT min_lon,min_lat,max_lon,max_lat,status FROM bounds WHERE dataset_id=? AND stage=? AND component IS NULL AND layer_name IS NULL AND kind='geometry'",(dataset,stage)).fetchone()
                dest[dataset]=list(row[:4]) if row and row[4]=='measured' else None
            boxes={kind:[a,b,c,e] if a is not None else None for kind,a,b,c,e in self.con.execute("SELECT kind,min_lon,min_lat,max_lon,max_lat FROM bounds WHERE dataset_id=? AND stage='configuration'",(dataset,))}
            self.configured[dataset]=boxes.get('profile') or boxes.get('rule') or boxes.get('normalization_manifest')

    def save_source_cache(self):
        cache=self.data/'.analysis_cache/audit_source_bounds.json'
        cache.parent.mkdir(parents=True,exist_ok=True)
        payload={'key':self.source_cache_key(),
                 'bounds':self.con.execute("SELECT * FROM bounds WHERE stage!='tiles'").fetchall(),
                 'checks':self.con.execute('SELECT * FROM bounds_checks WHERE variant IS NULL').fetchall()}
        partial=cache.with_suffix('.partial')
        partial.write_text(json.dumps(payload),encoding='utf-8')
        partial.replace(cache)

    def load_source_cache(self):
        cache=self.data/'.analysis_cache/audit_source_bounds.json'
        if not cache.exists(): return False
        saved=json.loads(cache.read_text(encoding='utf-8'))
        if saved['key']!=self.source_cache_key(): return False
        self.con.executemany('INSERT INTO bounds VALUES ('+','.join('?'*20)+')',saved['bounds'])
        self.con.executemany('INSERT INTO bounds_checks VALUES ('+','.join('?'*12)+')',saved['checks'])
        self.restore_source_references()
        self.con.commit()
        print('Bounds: verified source/config/GPKG cache reused; archive validation is rerun',flush=True)
        return True

    def issue(self, dataset, variant, coord, category, layer=None, details=None):
        # Keep complete counts in validation; cap detail examples per pair.
        count = self.issue_counts[dataset,variant]
        if count < 200:
            self.con.execute('INSERT INTO validation_issues VALUES (?,?,?,?,?,?,?,?)',
                (dataset, variant, *coord, category, layer, json.dumps(details or {})))
            self.issue_counts[dataset,variant] += 1

    def pair(self, d, variant):
        dataset = d['id']
        paths = {fmt: self.root/'app/data/output'/f'{dataset}_{variant}_{fmt.lower()}.pmtiles' for fmt in ('MVT', 'MLT')}
        started = time.monotonic()
        print(f'Full validation: {dataset} / {variant}', flush=True)
        # Addresses/offsets come from the actual archive directories, not metadata bounds.
        runs, headers = {}, {}
        for fmt, path in paths.items():
            header = headers[fmt] = core.read_pmtiles_header(path)
            indexed = runs[fmt] = {}
            with path.open('rb') as stream:
                for run in core._iter_tile_runs_from_handle(stream, header):
                    for delta in range(run.run_length):
                        coord = core.tileid_to_zxy(run.tile_id+delta)
                        if coord in indexed: raise ValueError(f'Duplicate tile address: {path}: {coord}')
                        indexed[coord] = (run.offset, run.length)
            self.record(dataset, 'tiles', 'archive_header', [header.min_lon, header.min_lat, header.max_lon, header.max_lat], path,
                        'PMTiles v3 header; descriptive, not actual geometry bounds', variant=variant, fmt=fmt)
            metadata = core.read_pmtiles_metadata(path, header)
            meta_box = metadata.get('bounds')
            try:
                meta_box = [float(v) for v in meta_box.split(',')] if isinstance(meta_box, str) else meta_box
            except (ValueError, TypeError): meta_box = None
            self.record(dataset, 'tiles', 'archive_metadata', meta_box, path, 'PMTiles metadata bounds', variant=variant, fmt=fmt)
            per_zoom = defaultdict(list)
            for z, x, y in indexed: per_zoom[z].append(tile_bounds(z, x, y))
            for z, boxes in per_zoom.items():
                self.record(dataset, 'tiles', 'tile_coverage', union(boxes), path, 'union of addressed Web Mercator cells', variant=variant, fmt=fmt, zoom=z)
            self.record(dataset, 'tiles', 'tile_coverage', union([union(v) for v in per_zoom.values()]), path,
                        'union of addressed cells across all zooms; may greatly exceed content', variant=variant, fmt=fmt)
        expected_extent = VARIANTS[variant][0]
        missing_mvt = set(runs['MLT'])-set(runs['MVT'])
        missing_mlt = set(runs['MVT'])-set(runs['MLT'])
        mismatches, errors, checked = len(missing_mvt)+len(missing_mlt), 0, 0
        geometry = {fmt: {} for fmt in paths}
        coverage_errors = defaultdict(int)
        for coord in sorted(missing_mvt): self.issue(dataset, variant, coord, 'missing_mvt')
        for coord in sorted(missing_mlt): self.issue(dataset, variant, coord, 'missing_mlt')
        with paths['MVT'].open('rb') as mvt, paths['MLT'].open('rb') as mlt:
            streams = {'MVT': mvt, 'MLT': mlt}
            previous, cached, raw_cached = {}, {}, {}
            last_progress = time.monotonic()
            for index, coord in enumerate(sorted(set(runs['MVT']) | set(runs['MLT']))):
                z, x, y = coord
                decoded, bad, decode_error = {}, False, False
                for fmt, path in paths.items():
                    if coord not in runs[fmt]: continue
                    key = runs[fmt][coord]
                    try:
                        # Adjacent deduplicated addresses may reuse decoded content.
                        if previous.get(fmt) != key:
                            h = headers[fmt]
                            raw = core._decompress(core._read_section(streams[fmt], h.tile_data_offset+key[0], key[1]), h.tile_compression, str(path))
                            cached[fmt] = decoded_tile(raw, fmt)
                            raw_cached[fmt] = raw
                            previous[fmt] = key
                        content, extents, boxes, counts = decoded[fmt] = cached[fmt]
                        for layer, local in boxes.items():
                            extent = extents[layer]
                            if extent != expected_extent:
                                bad = True
                                self.issue(dataset, variant, coord, 'coordinate_extent', layer, {'expected': expected_extent, 'actual': extent, 'format': fmt})
                            if local is not None:
                                b = tile_bounds(z, x, y, local, extent)
                                group = (z, layer)
                                geometry[fmt][group] = union([geometry[fmt].get(group), b])
                                buffer = 80 * (2 ** VARIANTS[variant][1])
                                if min(local) < -buffer-1 or max(local) > extent+buffer+1:
                                    coverage_errors[fmt, z] += 1
                    except Exception as error:
                        decode_error = True
                        previous.pop(fmt, None)
                        self.issue(dataset, variant, coord, 'decode_error', details={'format': fmt, 'error': f'{type(error).__name__}: {error}'})
                if coord in runs['MVT'] and coord in runs['MLT']:
                    if decode_error:
                        errors += 1
                    else:
                        checked += 1
                        left, right = decoded['MVT'], decoded['MLT']
                        if set(left[0]) != set(right[0]):
                            bad = True
                            self.issue(dataset, variant, coord, 'layer_names', details={'mvt': sorted(left[0]), 'mlt': sorted(right[0])})
                        for layer in set(left[0]) & set(right[0]):
                            if left[0][layer] != right[0][layer] or left[1][layer] != right[1][layer]:
                                bad = True
                                ring_diagnostic=None
                                if self.issue_counts[dataset,variant] < 200:
                                    try:
                                        ring_diagnostic=polygon_wire_signature(raw_cached['MVT'],'MVT').get(layer)==polygon_wire_signature(raw_cached['MLT'],'MLT').get(layer)
                                    except Exception:
                                        pass
                                self.issue(dataset, variant, coord, 'decoded_content', layer,
                                    {'mvt_features': left[3][layer], 'mlt_features': right[3][layer],
                                     'mvt_unmatched': sum((left[0][layer]-right[0][layer]).values()),
                                     'mlt_unmatched': sum((right[0][layer]-left[0][layer]).values()),
                                     'polygon_wire_rings_equal_diagnostic_only':ring_diagnostic})
                        mismatches += int(bad)
                elif decode_error: errors += 1
                if index and (index % 1000 == 0 or time.monotonic()-last_progress >= 15):
                    print(f'  {dataset}/{variant}: {index} addresses; mismatches={mismatches}; errors={errors}', flush=True)
                    last_progress = time.monotonic()
        for fmt, groups in geometry.items():
            per_zoom = defaultdict(list)
            for (z, layer), box in sorted(groups.items()):
                self.record(dataset, 'tiles', 'geometry', box, paths[fmt], 'union of independently decoded tile geometry envelopes',
                            variant=variant, fmt=fmt, layer=layer, zoom=z)
                per_zoom[z].append(box)
            for z, boxes in per_zoom.items():
                box = union(boxes)
                self.record(dataset, 'tiles', 'geometry', box, paths[fmt], 'union of layer geometry envelopes', variant=variant, fmt=fmt, zoom=z)
                # One full grid unit in longitude is also a conservative latitude tolerance.
                self.containment(dataset, 'tile_geometry_within_normalized', box, self.normalized_bounds.get(dataset),
                                 360/(2**z*expected_extent), variant=variant, fmt=fmt, zoom=z)
                count = coverage_errors[fmt, z]
                self.con.execute('INSERT INTO bounds_checks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (dataset, variant, fmt, z, 'geometry_within_tile_buffer', 'pass' if not count else 'fail', None,
                     None, None, None, None, f'{count} layer occurrences outside configured buffer plus one grid unit'))
            self.record(dataset, 'tiles', 'geometry', union(list(groups.values())), paths[fmt], 'union across all decoded layers and zooms', variant=variant, fmt=fmt)
        passed = int(not mismatches and not errors and checked == len(runs['MVT']) == len(runs['MLT']) and checked > 0)
        self.con.execute('INSERT INTO validation VALUES (' + ','.join('?'*18) + ')',
            (dataset, variant, 'full', self.relative(paths['MVT']), self.relative(paths['MLT']),
             self.digest(paths['MVT']), self.digest(paths['MLT']), len(runs['MVT']), len(runs['MLT']), checked,
             mismatches, errors, len(missing_mvt), len(missing_mlt), passed, 'pass' if passed else 'fail',
             time.monotonic()-started, datetime.now(timezone.utc).isoformat()))
        self.con.commit()
        print(f'  Finished: {checked} compared; mismatches={mismatches}; errors={errors}', flush=True)


def pair_job(job):
    path, root, data, dataset, variant, normalized = job
    audit = Audit(path, root, data, [dataset])
    audit.normalized_bounds = normalized
    try:
        audit.pair(dataset, variant)
        return path
    finally:
        audit.con.close()
        polygon_wire_signature.cache_clear()


def launch_pair_job(job):
    # File-based IPC works in restricted Windows environments where multiprocessing
    # named pipes are unavailable. Only independent pair workers share CPU, not DBs.
    description=Path(job[0]).with_suffix('.job.json')
    description.write_text(json.dumps(job),encoding='utf-8')
    subprocess.run([sys.executable,'-u','-m','analysis.audit','--pair-job',str(description)],
                   cwd=Path(__file__).resolve().parents[1],check=True)
    description.unlink()
    return job[0]


def project_source_crs_fallback(con, root):
    """Keep undeclared source CRS unknown, alongside projection under pipeline settings."""
    config=Path(root)/'app/converter/config.yaml'
    if not config.exists(): return
    fallback=(yaml.safe_load(config.read_text(encoding='utf-8')) or {}).get('citygml_fallback_source_srs')
    if not fallback: return
    config_hash=hashlib.sha256(config.read_bytes()).hexdigest()
    transformer=Transformer.from_crs(fallback,4326,always_xy=True)
    datasets=set()
    rows=con.execute("SELECT id,dataset_id,component,layer_name,native_bounds_json,path,sha256 FROM bounds WHERE stage='source' AND kind='geometry' AND layer_name IS NOT NULL AND native_crs IS NULL AND component LIKE '%.gml'").fetchall()
    for identifier,dataset,component,layer,native_text,path,digest in rows:
        native=json.loads(native_text)
        if not finite_bounds(native): continue
        box=list(transformer.transform_bounds(*native,densify_pts=21))
        if not finite_bounds(box): continue
        existing=con.execute("SELECT 1 FROM bounds WHERE dataset_id=? AND kind='geometry_pipeline_crs' AND component=? AND layer_name=?",(dataset,component,layer)).fetchone()
        if existing: continue
        details={'declared_crs':None,'crs_used':str(fallback),'crs_origin':'current converter fallback',
                 'config_path':config.relative_to(root).as_posix(),'config_sha256':config_hash,
                 'source_bounds_record':identifier,'historical_run_proven':False}
        con.execute('INSERT INTO bounds VALUES (NULL,'+','.join('?'*19)+')',
            (dataset,'source',None,None,'geometry_pipeline_crs',component,layer,None,*box,
             str(fallback),native_text,path,digest,'native feature envelopes projected using explicit converter CRS fallback',
             'projected_with_pipeline_crs',json.dumps(details)))
        datasets.add(dataset)
    for dataset in datasets:
        boxes=[];complete=True
        for component,layer,a,b,c,d,native in con.execute("SELECT component,layer_name,min_lon,min_lat,max_lon,max_lat,native_bounds_json FROM bounds WHERE dataset_id=? AND stage='source' AND kind='geometry' AND layer_name IS NOT NULL",(dataset,)):
            box=[a,b,c,d] if all(v is not None for v in (a,b,c,d)) else None
            if not finite_bounds(box):
                projected=con.execute("SELECT min_lon,min_lat,max_lon,max_lat FROM bounds WHERE dataset_id=? AND kind='geometry_pipeline_crs' AND component=? AND layer_name=?",(dataset,component,layer)).fetchone()
                if projected:box=list(projected)
                elif finite_bounds(json.loads(native)):complete=False
            if finite_bounds(box):boxes.append(box)
        total=union(boxes)
        original=con.execute("SELECT path,sha256 FROM bounds WHERE dataset_id=? AND stage='source' AND kind='geometry' AND component IS NULL AND layer_name IS NULL",(dataset,)).fetchone()
        con.execute('INSERT INTO bounds VALUES (NULL,'+','.join('?'*19)+')',
            (dataset,'source',None,None,'geometry_pipeline_crs',None,None,None,*(total or [None]*4),
             None,'null',*original,'union of declared-CRS and pipeline-fallback projected source envelopes',
             'projected_with_pipeline_crs' if complete and total else 'partial',
             json.dumps({'complete':complete,'config_path':config.relative_to(root).as_posix(),
                         'config_sha256':config_hash,'crs_used':str(fallback),'historical_run_proven':False})))
        norm=con.execute("SELECT min_lon,min_lat,max_lon,max_lat FROM bounds WHERE dataset_id=? AND stage='normalized' AND kind='geometry' AND layer_name IS NULL AND component IS NULL",(dataset,)).fetchone()
        if norm and any(v is None for v in norm): norm=None
        excess=([max(0,total[0]-norm[0]),max(0,total[1]-norm[1]),max(0,norm[2]-total[2]),max(0,norm[3]-total[3])]
                if complete and finite_bounds(total) and finite_bounds(norm) else None)
        con.execute('INSERT INTO bounds_checks VALUES ('+','.join('?'*12)+')',
            (dataset,None,None,None,'normalized_within_source_pipeline_crs',
             'unknown' if excess is None else ('pass' if max(excess)<=1e-5 else 'fail'),1e-5,
             *(excess or [None]*4),'Source envelopes projected with explicit current pipeline CRS fallback; raw file CRS remains undeclared'))
    con.commit()


def finalize_geometry_status(con):
    """Never present an envelope from incompletely decoded tiles as complete."""
    missing=con.execute("""SELECT c.dataset_id,c.variant,c.format,c.zoom,c.path,c.sha256
        FROM bounds c WHERE c.kind='tile_coverage' AND c.zoom IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM bounds g WHERE g.dataset_id=c.dataset_id
          AND g.variant=c.variant AND g.format=c.format AND g.zoom=c.zoom
          AND g.kind='geometry' AND g.layer_name IS NULL)""").fetchall()
    for dataset,variant,fmt,zoom,path,digest in missing:
        con.execute('INSERT INTO bounds VALUES (NULL,'+','.join('?'*19)+')',
            (dataset,'tiles',variant,fmt,'geometry',None,None,zoom,
             None,None,None,None,None,'null',path,digest,
             'no finite decoded geometry at this zoom','unknown',
             json.dumps({'reason':'No finite geometry envelope available; consult validation errors and tile content.'})))
        for name in ('tile_geometry_within_normalized','geometry_within_tile_buffer'):
            con.execute('INSERT INTO bounds_checks VALUES ('+','.join('?'*12)+')',
                (dataset,variant,fmt,zoom,name,'unknown',None,None,None,None,None,
                 'No finite decoded geometry envelope at this zoom'))
    for dataset,variant,errors in con.execute('SELECT dataset_id,variant,errors FROM validation WHERE errors>0').fetchall():
        issues=con.execute("SELECT z,x,y,details_json FROM validation_issues WHERE dataset_id=? AND variant=? AND category='decode_error'",(dataset,variant)).fetchall()
        complete_examples=len({(z,x,y) for z,x,y,_ in issues})==errors
        failed=defaultdict(set)
        for z,_,_,details in issues:
            failed[json.loads(details)['format']].add(z)
        for fmt in ('MVT','MLT'):
            if complete_examples and not failed[fmt]: continue
            rows=con.execute("SELECT id,zoom,details_json FROM bounds WHERE dataset_id=? AND variant=? AND format=? AND kind='geometry'",(dataset,variant,fmt)).fetchall()
            for identifier,zoom,details in rows:
                if complete_examples and zoom is not None and zoom not in failed[fmt]: continue
                info=json.loads(details);info['incomplete_pair_decode']=True;info['pair_error_addresses']=errors
                con.execute("UPDATE bounds SET status=CASE WHEN min_lon IS NULL THEN 'unknown' ELSE 'partial' END,details_json=? WHERE id=?",(json.dumps(info),identifier))
            checks=con.execute("SELECT rowid,zoom FROM bounds_checks WHERE dataset_id=? AND variant=? AND format=? AND status='pass'",(dataset,variant,fmt)).fetchall()
            for identifier,zoom in checks:
                if complete_examples and zoom not in failed[fmt]: continue
                con.execute("UPDATE bounds_checks SET status='unknown',message=message||'; incomplete decoding at this zoom' WHERE rowid=?",(identifier,))
    con.commit()


def build(target, root, data, datasets, workers=None):
    audit = Audit(target, root, data, datasets)
    try:
        if not audit.load_source_cache():
            audit.sources_and_normalized()
            audit.save_source_cache()
        workers = min(3, os.cpu_count() or 1) if workers is None else workers
        if workers < 1: raise ValueError('workers must be positive')
        if workers == 1:
            for dataset in datasets:
                for variant in VARIANTS: audit.pair(dataset, variant)
        else:
            folder=Path(data)/'.analysis_cache'/('audit-jobs-'+uuid.uuid4().hex)
            folder.mkdir(parents=True)
            jobs=[(str(folder/f'{i}-{variant}.sqlite'),str(root),str(data),dataset,variant,audit.normalized_bounds)
                  for i,dataset in enumerate(datasets) for variant in VARIANTS]
            print(f'Full pair audit: {workers} worker processes',flush=True)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                # Merge in registry/variant order, independent of worker scheduling.
                for path in pool.map(launch_pair_job,jobs):
                    with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True)) as source:
                        for table in ('bounds','bounds_checks','validation','validation_issues'):
                            columns=[r[1] for r in audit.con.execute(f'PRAGMA table_info({table})') if r[1]!='id']
                            names=','.join(columns)
                            audit.con.executemany(f'INSERT INTO {table} ({names}) VALUES ('+','.join('?'*len(columns))+')',
                                                  source.execute(f'SELECT {names} FROM {table} ORDER BY rowid').fetchall())
                    audit.con.commit()
                    Path(path).unlink()
            folder.rmdir()  # Only an empty directory owned by this invocation.
        project_source_crs_fallback(audit.con, root)
        finalize_geometry_status(audit.con)
    finally:
        audit.con.close()


if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--pair-job':
        raise SystemExit('Run through management.py audit')
    pair_job(json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')))
