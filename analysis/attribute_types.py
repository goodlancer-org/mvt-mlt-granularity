"""Address-weighted MVT wire types -> MLT declared column types, without feature matching.

Profiles are stored once per unique pair of payload locations. Addresses reference
the pair; summaries weight every profile by its number of addressed tiles.
"""
from collections import Counter, defaultdict
from contextlib import closing
import json
import sqlite3

from mapbox_vector_tile.Mapbox import vector_tile_pb2

from . import output_analysis_core as core

TABLES = ('attribute_payload_pairs', 'attribute_tile_addresses', 'attribute_type_profiles',
          'attribute_type_errors', 'attribute_transitions', 'attribute_type_summary')


def mvt_profiles(raw):
    tile = vector_tile_pb2.tile()
    tile.ParseFromString(raw)
    layers = {}
    for layer in tile.layers:
        if layer.name in layers:
            raise ValueError(f'Ambiguous duplicate MVT layer: {layer.name}')
        fields = defaultdict(Counter)
        present = Counter()
        examples = defaultdict(list)
        values = []
        for value in layer.values:
            populated = value.ListFields()
            if len(populated) != 1:
                raise ValueError('MVT Value must have exactly one typed field')
            descriptor, actual = populated[0]
            values.append((descriptor.name.removesuffix('_value'), actual))
        for feature in layer.features:
            if len(feature.tags) % 2:
                raise ValueError('Odd MVT feature tag count')
            seen = set()
            for i in range(0, len(feature.tags), 2):
                name = layer.keys[feature.tags[i]]
                if name in seen:
                    raise ValueError(f'Duplicate property key on MVT object: {name}')
                seen.add(name)
                kind, actual = values[feature.tags[i+1]]
                fields[name][kind] += 1
                present[name] += 1
                bucket = examples[name, kind]
                # Text representation is diagnostic; it never determines type.
                if len(bucket) < 3 and str(actual)[:160] not in bucket:
                    bucket.append(str(actual)[:160])
        layers[layer.name] = (len(layer.features), fields, present, examples)
    return layers


def mlt_columns(raw):
    """Read only v1 frame metadata; no native geometry decoder or stream inflation."""
    layers = {}
    position = 0
    while position < len(raw):
        size, start = core._read_mlt_varint(raw, position, len(raw))
        end = start + size
        if size < 1 or end > len(raw):
            raise ValueError('Invalid MLT frame length')
        if raw[start] != core.MLT_V1_TAG:
            raise ValueError(f'Unsupported MLT frame tag: {raw[start]}')
        name, cursor = core._read_mlt_string(raw, start+1, end)
        _, cursor = core._read_mlt_varint(raw, cursor, end)  # extent
        count, cursor = core._read_mlt_varint(raw, cursor, end)
        if name in layers:
            raise ValueError(f'Ambiguous duplicate MLT layer: {name}')
        columns = layers[name] = {}
        for _ in range(count):
            column, cursor = core._parse_mlt_column_meta(raw, cursor, end)
            if column.type_code in (0, 1, 2, 3, 4):
                continue  # ID and geometry are not properties named "id"/"geometry".
            children = column.children if column.type_code == 30 else (column,)
            for child in children:
                full_name = column.name + child.name if column.type_code == 30 else child.name
                if full_name in columns:
                    raise ValueError(f'Ambiguous duplicate MLT column: {full_name}')
                columns[full_name] = (child.type_name, int(child.nullable),
                                      'SharedDict' if column.type_code == 30 else 'Scalar')
        position = end
    return layers


def relation(before, after):
    base = after.removeprefix('Opt')
    if before == 'absent':
        return 'mlt_only_column'
    if after == 'absent':
        return 'missing_mlt_column'
    if base == 'String':
        return 'string_retained' if before == 'string' else 'to_string'
    if base == 'Bool':
        return 'bool_retained' if before == 'bool' else 'other_type_change'
    if base in ('Int32', 'UInt32', 'Int64', 'UInt64', 'Float', 'Double'):
        return 'numeric_representation' if before in ('int', 'uint', 'sint', 'float', 'double') else 'other_type_change'
    return 'other_type_change'


def compare_profiles(left, right):
    rows = []
    for layer in sorted(left.keys() | right.keys()):
        n, fields, present, examples = left.get(layer, (0, {}, {}, {}))
        columns = right.get(layer, {})
        for field in sorted(fields.keys() | columns.keys()):
            after, nullable, storage = columns.get(field, ('absent', None, None))
            types = fields.get(field, {})
            for before, occurrences in (types.items() if types else [('absent', 0)]):
                rows.append((layer, field, before, after, nullable, storage, occurrences,
                             n, n-present.get(field, 0), len(types), relation(before, after),
                             json.dumps(examples.get((field, before), []), ensure_ascii=False)))
    return rows


def build(target, root, datasets):
    with closing(sqlite3.connect(target)) as con, con:
        con.executescript('''
          CREATE TABLE attribute_payload_pairs(pair_id INTEGER PRIMARY KEY,dataset_id TEXT,
            variant TEXT,mvt_offset INTEGER,mvt_length INTEGER,mlt_offset INTEGER,mlt_length INTEGER,
            address_count INTEGER,status TEXT);
          CREATE TABLE attribute_tile_addresses(pair_id INTEGER,z INTEGER,x INTEGER,y INTEGER);
          CREATE TABLE attribute_type_profiles(pair_id INTEGER,layer_name TEXT,property_name TEXT,
            before_type TEXT,after_type TEXT,after_nullable INTEGER,after_storage TEXT,
            value_count INTEGER,mvt_features INTEGER,absent_count INTEGER,source_type_count INTEGER,
            transition TEXT,before_examples_json TEXT);
          CREATE TABLE attribute_type_errors(pair_id INTEGER,format TEXT,message TEXT);
        ''')
        for dataset in datasets:
            for variant in ('standard', 'dense4', 'dense16'):
                paths = {fmt: root/'app/data/output'/f"{dataset['id']}_{variant}_{fmt.lower()}.pmtiles"
                         for fmt in ('MVT', 'MLT')}
                headers, addresses = {}, {}
                for fmt, path in paths.items():
                    headers[fmt] = core.read_pmtiles_header(path)
                    index = addresses[fmt] = {}
                    with path.open('rb') as stream:
                        for run in core._iter_tile_runs_from_handle(stream, headers[fmt]):
                            for delta in range(run.run_length):
                                coord = core.tileid_to_zxy(run.tile_id+delta)
                                if coord in index:
                                    raise ValueError(f'Duplicate tile address: {path}: {coord}')
                                index[coord] = (run.offset, run.length)
                groups = defaultdict(list)
                for coord in sorted(addresses['MVT'].keys() | addresses['MLT'].keys()):
                    groups[addresses['MVT'].get(coord), addresses['MLT'].get(coord)].append(coord)
                print(f"Attribute types: {dataset['id']}/{variant}: {len(groups)} payload pairs", flush=True)
                with paths['MVT'].open('rb') as mvt, paths['MLT'].open('rb') as mlt:
                    streams = {'MVT': mvt, 'MLT': mlt}
                    for index, ((mkey, lkey), coords) in enumerate(groups.items()):
                        pair = con.execute('INSERT INTO attribute_payload_pairs VALUES (NULL,?,?,?,?,?,?,?,?)',
                            (dataset['id'], variant, *(mkey or (None,None)), *(lkey or (None,None)), len(coords), 'pending')).lastrowid
                        con.executemany('INSERT INTO attribute_tile_addresses VALUES (?,?,?,?)', [(pair,*c) for c in coords])
                        parsed = {}
                        for fmt, key in (('MVT', mkey), ('MLT', lkey)):
                            try:
                                if key is None:
                                    raise ValueError('Missing addressed tile')
                                h = headers[fmt]
                                raw = core._decompress(core._read_section(streams[fmt],h.tile_data_offset+key[0],key[1]), h.tile_compression,str(paths[fmt]))
                                parsed[fmt] = mvt_profiles(raw) if fmt == 'MVT' else mlt_columns(raw)
                            except Exception as error:
                                con.execute('INSERT INTO attribute_type_errors VALUES (?,?,?)', (pair,fmt,f'{type(error).__name__}: {error}'))
                        if len(parsed) == 2:
                            con.executemany('INSERT INTO attribute_type_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                [(pair,*r) for r in compare_profiles(parsed['MVT'],parsed['MLT'])])
                        con.execute('UPDATE attribute_payload_pairs SET status=? WHERE pair_id=?', ('measured' if len(parsed)==2 else 'unknown',pair))
                        if index and index % 1000 == 0:
                            print(f'  {index}/{len(groups)} payload pairs', flush=True)
                    con.commit()
        con.executescript('''
          CREATE INDEX attribute_profile_pair ON attribute_type_profiles(pair_id);
          CREATE INDEX attribute_address_pair ON attribute_tile_addresses(pair_id);
          CREATE TABLE attribute_transitions AS
            SELECT p.dataset_id,p.variant,t.layer_name,t.property_name,t.before_type,t.after_type,
              t.after_nullable,t.after_storage,t.transition,
              SUM(p.address_count) AS column_type_tile_occurrences,
              SUM(t.value_count*p.address_count) AS value_occurrences,
              SUM(CASE WHEN t.source_type_count>1 THEN t.value_count*p.address_count ELSE 0 END) AS mixed_source_value_occurrences
            FROM attribute_type_profiles t JOIN attribute_payload_pairs p USING(pair_id)
            GROUP BY 1,2,3,4,5,6,7,8,9;
          CREATE TABLE attribute_type_summary AS
            WITH columns AS (
              SELECT pair_id,layer_name,property_name,MAX(source_type_count>1) AS mixed,
                SUM(value_count) AS n_values,
                SUM(CASE WHEN transition='to_string' THEN value_count ELSE 0 END) AS n_to_string,
                MAX(after_type='absent') AS missing,MAX(before_type='absent') AS added
              FROM attribute_type_profiles GROUP BY 1,2,3
            )
            SELECT p.dataset_id,p.variant,SUM(p.address_count) AS property_tile_occurrences,
              SUM(c.mixed*p.address_count) AS mixed_property_tile_occurrences,
              SUM(c.n_values*p.address_count) AS value_occurrences,
              SUM(c.n_to_string*p.address_count) AS to_string_value_occurrences,
              SUM(c.missing*p.address_count) AS missing_column_tile_occurrences,
              SUM(c.added*p.address_count) AS mlt_only_column_tile_occurrences
            FROM columns c JOIN attribute_payload_pairs p USING(pair_id) GROUP BY 1,2;
        ''')
