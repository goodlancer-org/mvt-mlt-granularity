"""Primary extended experiment: immutable per-payload Parquet and matched-block SQL.

Conversion is ``python -m src.experiment`` inside Docker; this module performs
measurement ingestion, comparisons and reports without re-encoding any tile.
"""
from __future__ import annotations
from collections import defaultdict
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from .pipeline import ROOT, DATA, registry

VARIANTS={'standard':0,'aggregated4':1,'aggregated16':2,'dense4':1,'dense16':2}
FORMATS=('mvt','mltv1','mltv2')
EXT=DATA/'extended'
ANALYSIS_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
SCHEMAS={
    'addresses':'dataset:string variant:string factor:int64 z:int64 x:int64 y:int64 logical_z:int64 payload_key:string stored_mvt_bytes:int64',
    'payloads':'dataset:string variant:string payload_key:string format:string raw_bytes:int64 gzip_bytes:int64 content_sha256:string',
    'content':'dataset:string variant:string payload_key:string layer:string extent:int64 feature_instances:int64 vertices:int64 fragments:int64 unique_source_features:int64 repeated_instances:int64 unique_id_coordinates:int64 repeated_vertices:int64',
    'feature_ids':'dataset:string variant:string payload_key:string layer:string source_id:int64 instances:int64',
    'streams':'dataset:string variant:string payload_key:string format:string layer_index:int64 offset:int64 payload_bytes:int64 num_values:int64 stream_type:string logical:string physical:string',
    'frames':'dataset:string variant:string payload_key:string format:string layer_index:int64 layer:string frame_bytes:int64',
    'attributes':'dataset:string variant:string payload_key:string format:string layer:string property:string source_type:string imported_type:string occurrences:int64',
    'validation':'dataset:string variant:string payload_key:string format:string roundtrip_passed:bool differences:string source_features:int64 imported_features:int64 source_vertices:int64 imported_vertices:int64',
    'equivalence':'dataset:string variant:string z:int64 x:int64 y:int64 logical_z:int64 children:int64 features:int64 vertices:int64 fragments:int64 passed:bool',
}


def schema(name):
    return pa.schema([(key,getattr(pa,'bool_' if typ=='bool' else typ)()) for key,typ in
                      (item.split(':') for item in SCHEMAS[name].split())])


class Tables:
    def __init__(self,root,part): self.root=root;self.part=part;self.buffers=defaultdict(list);self.writers={}
    def add(self,name,row):
        self.buffers[name].append(row)
        if len(self.buffers[name])>=20000:self.flush(name)
    def flush(self,name):
        rows=self.buffers[name]
        if not rows:return
        if name not in self.writers:
            folder=self.root/name;folder.mkdir(parents=True,exist_ok=True)
            self.writers[name]=pq.ParquetWriter(folder/(self.part+'.parquet'),schema(name),compression='zstd')
        self.writers[name].write_table(pa.Table.from_pylist(rows,schema=schema(name)));rows.clear()
    def close(self):
        for name in list(self.buffers):self.flush(name)
        for w in self.writers.values():w.close()


def ingest_one(dataset,variant,root=EXT):
    from .release import sha256
    output=ROOT/'app/data/output';stem=f'{dataset}_{variant}_mvt'
    measurement=output/(stem+'.measurements.jsonl.gz')
    manifest=json.loads((output/(stem+'.experiment.json')).read_text())
    for filename,info in manifest['archives'].items():
        archive=output/filename
        if sha256(archive)!=info['sha256']:raise ValueError(f'Archive changed since measurement: {filename}')
    digest=sha256(measurement)
    if digest!=manifest['measurements_sha256']:raise ValueError(f'Measurement hash differs: {measurement}')
    evidence=None
    if variant.startswith('aggregated'):
        evidence=output/(stem+'.aggregation.jsonl.gz')
        receipt=json.loads((output/(stem+'.aggregation.json')).read_text())
        standard=output/f'{dataset}_standard_mvt.pmtiles'
        if (receipt['evidence_sha256']!=sha256(evidence) or
                receipt['archive_sha256']!=manifest['inputs']['mvt_sha256'] or
                receipt['inputs']['standard_sha256']!=sha256(standard)):
            raise ValueError(f'Aggregation evidence or input changed: {dataset}/{variant}')
    marker=root/'manifests'/f'{dataset}_{variant}.json';marker.parent.mkdir(parents=True,exist_ok=True)
    identity={'manifest':manifest,'measurement_sha256':digest,
        'analysis_sha256':ANALYSIS_SHA256}
    if marker.exists() and json.loads(marker.read_text())==identity:return
    tables=Tables(root,f'{dataset}_{variant}')
    common={'dataset':dataset,'variant':variant}
    lookup=ROOT/'app/data/provenance'/f'{dataset}.provenance.sqlite'
    valid_ids=None
    if lookup.exists():
        with sqlite3.connect(lookup) as db:valid_ids={r[0] for r in db.execute('SELECT id FROM feature_provenance')}
        db.close()
    with gzip.open(measurement,'rt',encoding='utf-8') as stream:
        for line in stream:
            record=json.loads(line);key=record['payload_key'];base={**common,'payload_key':key}
            if record['kind']=='address':
                z,x,y=record['zxy']
                tables.add('addresses',{**base,'factor':4**VARIANTS[variant],'z':z,'x':x,'y':y,
                    'logical_z':record['logical_zoom'],'stored_mvt_bytes':record['stored_mvt_bytes']})
                continue
            tables.add('payloads',{**base,'format':'mvt','raw_bytes':record['mvt_raw_bytes'],
                'gzip_bytes':record['mvt_gzip_bytes'],'content_sha256':key})
            for layer in record['content']:
                tables.add('content',{**base,'layer':layer['name'],**{k:layer[k] for k in (
                    'extent','feature_instances','vertices','fragments','unique_source_features',
                    'repeated_instances','unique_id_coordinates','repeated_vertices')}})
                for source_id,count in layer['source_ids']:
                    if valid_ids is not None and source_id not in valid_ids:
                        raise ValueError(f'Tile source ID absent from provenance: {dataset}/{source_id}')
                    tables.add('feature_ids',{**base,'layer':layer['name'],'source_id':source_id,'instances':count})
            for fmt in record['formats']:
                fb={**base,'format':fmt['format']}
                tables.add('payloads',{**fb,'raw_bytes':fmt['raw_bytes'],'gzip_bytes':fmt['gzip_bytes'],
                    'content_sha256':fmt['payload_sha256']})
                for index,frame in enumerate(fmt['layers']):
                    name=json.loads(frame['label'].split('] ',1)[1])
                    tables.add('frames',{**fb,'layer_index':index,'layer':name,'frame_bytes':frame['frame_bytes']})
                for s in fmt['streams']:
                    tables.add('streams',{**fb,'layer_index':s['layer'],'offset':s['offset'],
                        'payload_bytes':s['payload_bytes'],'num_values':s['logical_values'],
                        'stream_type':s['streamType'],'logical':s['logical'],'physical':s['physical']})
                imported={l['name']:l for l in fmt['imported_layers']}
                for layer in record['content']:
                    target=imported.get(layer['name'],{})
                    kinds=dict(zip(target.get('property_names',[]),target.get('property_kinds',[])))
                    for prop,types in layer['property_types'].items():
                        for kind,count in types.items():
                            tables.add('attributes',{**fb,'layer':layer['name'],'property':prop,'source_type':kind,
                                'imported_type':kinds.get(prop,'absent'),'occurrences':count})
                tables.add('validation',{**fb,'roundtrip_passed':not fmt['roundtrip_differences'],
                    'differences':json.dumps(fmt['roundtrip_differences']),
                    'source_features':sum(l['feature_instances'] for l in record['content']),
                    'source_vertices':sum(l['vertices'] for l in record['content']),
                    'imported_features':sum(l['features'] for l in fmt['imported_layers']),
                    'imported_vertices':sum(l['vertices'] for l in fmt['imported_layers'])})
    if variant.startswith('aggregated'):
        with gzip.open(evidence,'rt',encoding='utf-8') as stream:
            for line in stream:
                r=json.loads(line);z,x,y=r['zxy']
                tables.add('equivalence',{**common,'z':z,'x':x,'y':y,'logical_z':r['logical_zoom'],
                    **{k:r[k] for k in ('children','features','vertices','fragments')},'passed':r['equivalent']})
    tables.close()
    marker.write_text(json.dumps(identity,indent=2)+'\n',encoding='utf-8')
    print(f'Ingested {dataset}/{variant}',flush=True)


def connect(root=EXT):
    con=duckdb.connect()
    con.execute("SET memory_limit='4GB'")
    for table in SCHEMAS:
        files=list((root/table).glob('*.parquet'))
        if files:
            pattern=(root/table/'*.parquet').as_posix().replace("'","''")
            con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{pattern}')")
        else:
            empty=pa.Table.from_pylist([],schema=schema(table));con.register(table,empty)
    return con


def statistics(root=EXT):
    from .release import sha256
    con=connect(root)
    sql=(Path(__file__).parent/'sql/extended.sql').read_text(encoding='utf-8')
    con.execute(sql)
    target=root/'results.sqlite';partial=target.with_suffix('.sqlite.partial');partial.unlink(missing_ok=True)
    with sqlite3.connect(partial) as db:
        for table in ('archive_summary','zoom_summary','savings','decomposition','decomposition_zoom',
                      'coverage','content_summary','content_differences','stream_summary','layer_summary',
                      'attribute_summary','validation_summary','aggregation_validation','vertex_bins','bytes_per_vertex'):
            description=con.execute(f'SELECT * FROM {table} LIMIT 0').description
            projection=','.join('CAST("'+name+'" AS BIGINT) AS "'+name+'"'
                if str(kind) in ('HUGEINT','UHUGEINT') else '"'+name+'"' for name,kind,*_ in description)
            # DuckDB SUM(int64) is int128. Its NumPy conversion would become
            # float64; explicitly retain exact integer counts/bytes in SQLite/CSV.
            frame=con.execute(f'SELECT {projection} FROM {table} ORDER BY ALL').fetchdf()
            frame.to_sql(table,db,index=False)
            with (DATA/f'extended_{table}.csv').open('w',encoding='utf-8',newline='') as out:
                frame.to_csv(out,index=False)
        db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
        db.executemany('INSERT INTO meta VALUES (?,?)',[
            ('schema','extended-experiment-v1'),('size_semantics','ratio of sums; raw and independent gzip-6 mtime=0'),
            ('decomposition','same geographic parent-block intersection at each logical zoom; additive bytes'),
            ('provenance','globally disjoint normalized source-layer FIDs; separate SQLite feature_provenance'),
            ('source_ids','unique within a logical zoom and region; no identification across source layers'),
            ('vertices','explicit MVT MoveTo/LineTo coordinates; implicit polygon closures excluded'),
            ('repeated_vertices','identical source-ID/coordinate occurrences within a comparison block; not a causal clipping estimate')])
        from .output_analysis_core import read_pmtiles_header
        from pmtiles.reader import MmapSource,Reader,all_tiles
        from pmtiles.tile import Compression
        import pandas as pd
        archives=[]
        for dataset,variant in con.execute('SELECT DISTINCT dataset,variant FROM addresses ORDER BY dataset,variant').fetchall():
            for fmt in FORMATS:
                path=ROOT/'app/data/output'/f'{dataset}_{variant}_{fmt}.pmtiles'
                header=read_pmtiles_header(path)
                expected=con.execute('''SELECT a.z,a.x,a.y,p.content_sha256,p.raw_bytes,p.gzip_bytes,a.stored_mvt_bytes
                    FROM addresses a JOIN payloads p USING(dataset,variant,payload_key)
                    WHERE a.dataset=? AND a.variant=? AND p.format=?''',(dataset,variant,fmt)).fetchall()
                wanted={(z,x,y):(digest,raw_size,gzip_size,stored_size)
                        for z,x,y,digest,raw_size,gzip_size,stored_size in expected}
                if len(wanted)!=len(expected):raise ValueError(f'Duplicate measured addresses: {path.name}')
                verified=actual_raw=actual_gzip=0
                with path.open('rb') as handle:
                    source=MmapSource(handle);compression=Reader(source).header()['tile_compression']
                    for zxy,payload in all_tiles(source):
                        info=wanted.pop(zxy,None)
                        if info is None:raise ValueError(f'Unexpected or duplicate archive address: {path.name}/{zxy}')
                        if compression==Compression.GZIP:raw=gzip.decompress(payload)
                        elif compression==Compression.NONE:raw=payload
                        else:raise ValueError(f'Unsupported archive compression: {path.name}')
                        digest=hashlib.sha256(raw if fmt=='mvt' else payload).hexdigest()
                        expected_gzip=info[3] if fmt=='mvt' else info[2]
                        if digest!=info[0] or len(raw)!=info[1] or len(payload)!=expected_gzip:
                            raise ValueError(f'Archive payload differs from verified measurement: {path.name}/{zxy}')
                        verified+=1;actual_raw+=len(raw);actual_gzip+=len(payload)
                if wanted:raise ValueError(f'Missing archive addresses: {path.name}: {len(wanted)}')
                archives.append({'dataset':dataset,'variant':variant,'format':fmt,'file_bytes':path.stat().st_size,
                    'stored_tile_data_bytes':header.tile_data_length,'stored_unique_payloads':header.tile_contents_count,
                    'verified_addresses':verified,'actual_address_raw_bytes':actual_raw,
                    'actual_address_gzip_bytes':actual_gzip,'address_payloads_match_measurements':True,
                    'sha256':sha256(path)})
        frame=pd.DataFrame(archives);frame.to_sql('physical_archives',db,index=False)
        frame.to_csv(DATA/'extended_physical_archives.csv',index=False)
    db.close();partial.replace(target);con.close()
    return target


def snapshot_history():
    from .release import sha256
    target=DATA/'historical/python-0.2.2'
    if (target/'snapshot.json').exists():return
    target.mkdir(parents=True,exist_ok=True);manifest={}
    for path in DATA.iterdir():
        if path.is_file() and (path.suffix in ('.csv','.sqlite','.json','.md') or path.name.endswith('.manifest.json')):
            shutil.copy2(path,target/path.name)
            manifest[path.name]=sha256(path)
    (target/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('tiles','stats','report','all'),default='all',nargs='?')
    parser.add_argument('--dataset',action='append')
    args=parser.parse_args(argv)
    snapshot_history()
    if args.stage in ('tiles','all'):
        for d in registry():
            if args.dataset and d['id'] not in args.dataset:continue
            for variant in VARIANTS:ingest_one(d['id'],variant)
    if args.stage in ('stats','all'):statistics()
    if args.stage in ('report','all'):
        from .extended_report import report
        report()
    return 0

if __name__=='__main__':raise SystemExit(main())
