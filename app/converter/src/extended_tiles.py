"""Five-variant research conversion, with exact aggregation and framed Rust encoding."""
from __future__ import annotations
from collections import Counter, OrderedDict
from contextlib import ExitStack
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time
from pmtiles.reader import MmapSource, Reader, all_tiles
from pmtiles import writer
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from .mvt_aggregate import aggregate_tiles, tile_message, geometry_counts

VARIANTS = {'standard':0,'aggregated4':1,'aggregated16':2,'dense4':1,'dense16':2}
FORMATS = ('mvt','mltv1','mltv2')


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''): digest.update(block)
    return digest.hexdigest()


def raw_payload(payload, compression):
    if compression == Compression.GZIP: return gzip.decompress(payload)
    if compression == Compression.NONE: return payload
    raise ValueError(f'Unsupported PMTiles compression: {compression}')


def cli_path():
    path = Path(os.environ.get('MLT_RUST_CLI', str(Path(__file__).parents[1]/'bin'/
                    ('mlt-experiment.exe' if os.name=='nt' else 'mlt-experiment'))))
    if not path.is_file(): raise RuntimeError('Build the Rust CLI: python app/converter/build_mlt_cli.py')
    return path.resolve()


class RustEncoder:
    def __enter__(self):
        self.process = subprocess.Popen([str(cli_path())], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        return self

    def _read(self):
        def exact(n):
            data=bytearray()
            while len(data)<n:
                chunk=self.process.stdout.read(n-len(data))
                if not chunk: raise RuntimeError(f'Rust encoder exited: {self.process.poll()}')
                data.extend(chunk)
            return bytes(data)
        length=struct.unpack('<I',exact(4))[0]
        return exact(length)

    def encode(self, raw):
        self.process.stdin.write(struct.pack('<I',len(raw))); self.process.stdin.write(raw); self.process.stdin.flush()
        stats=json.loads(self._read())
        if 'error' in stats: raise RuntimeError(stats['error'])
        return [self._read(),self._read()], stats['formats']

    def __exit__(self,*exc):
        self.process.stdin.close(); self.process.stdout.close()
        try: self.process.wait(timeout=10)
        except subprocess.TimeoutExpired: self.process.kill(); self.process.wait()
        if not exc[0] and self.process.returncode: raise RuntimeError(f'Rust encoder exit {self.process.returncode}')


def content_summary(raw):
    """Wire counts and observable ID/coordinate redundancy inside this encoding unit.

    A fragment is a MoveTo part (including rings and point components), not a
    claim that every part was created by clipping. Polygon closing coordinates
    are implicit and excluded from stored vertices.
    """
    result=[]
    for layer in tile_message(raw).layers:
        ids=Counter(); vertices=fragments=0; positions=set(); types=Counter(); property_types={}
        for feature in layer.features:
            if not feature.HasField('id'): raise ValueError('Missing provenance ID in regenerated MVT')
            ids[feature.id]+=1
            v,f=geometry_counts(feature.geometry); vertices+=v; fragments+=f
            x=y=0; pos=0
            while pos<len(feature.geometry):
                cmd=feature.geometry[pos];pos+=1
                if cmd&7 in (1,2):
                    for _ in range(cmd>>3):
                        dx,dy=feature.geometry[pos:pos+2];pos+=2
                        x+=(dx>>1)^-(dx&1);y+=(dy>>1)^-(dy&1)
                        positions.add((feature.id,x,y))
            for i in range(0,len(feature.tags),2):
                key=layer.keys[feature.tags[i]]; value=layer.values[feature.tags[i+1]]
                fields=value.ListFields()
                kind=fields[0][0].name if fields else 'empty'
                types[kind]+=1
                property_types.setdefault(key,Counter())[kind]+=1
        result.append({'name':layer.name,'extent':layer.extent,'feature_instances':len(layer.features),
            'vertices':vertices,'fragments':fragments,'source_ids':list(ids.items()),
            'unique_source_features':len(ids),'repeated_instances':len(layer.features)-len(ids),
            'unique_id_coordinates':len(positions),'repeated_vertices':vertices-len(positions),
            'value_types':dict(types),'property_types':{k:dict(v) for k,v in property_types.items()}})
    return result


def aggregate_archive(standard, target, offset, *, force=False):
    standard,target=Path(standard),Path(target)
    factor=2**offset
    evidence=target.with_suffix('.aggregation.jsonl.gz')
    receipt=target.with_suffix('.aggregation.json')
    identity={'standard_sha256':sha256(standard),'offset':offset,'aggregation':'exact-protobuf-multiset-v1'}
    if not force and receipt.exists() and target.exists() and evidence.exists():
        old=json.loads(receipt.read_text())
        if old['inputs']==identity and old['archive_sha256']==sha256(target) and old['evidence_sha256']==sha256(evidence):
            print(f'Up to date exact aggregation: {target.stem}',flush=True)
            return target
    with standard.open('rb') as source_file:
        source=MmapSource(source_file); reader=Reader(source); header=reader.header(); compression=header['tile_compression']
        def groups():
            # PMTiles Hilbert traversal keeps aligned quadtree children together.
            # Stream each block once: Reader.get would decompress/reparse the
            # same directory pages for every child. Assert order rather than
            # relying on that property silently.
            current=None;children=[];previous_id=-1
            for (z,x,y),payload in all_tiles(source):
                if z<offset:continue
                parent=(z-offset,x//factor,y//factor)
                if parent!=current:
                    if current is not None:yield current,children
                    parent_id=zxy_to_tileid(*parent)
                    if parent_id<=previous_id:raise ValueError('Non-contiguous or unordered parent blocks in PMTiles')
                    previous_id=parent_id;current=parent;children=[]
                children.append(((z,x,y),raw_payload(payload,compression)))
            if current is not None:yield current,children
        partial=target.with_suffix('.pmtiles.partial')
        evidence_partial=evidence.with_suffix('.gz.partial')
        with partial.open('wb') as stream, gzip.open(evidence_partial,'wt',encoding='utf-8') as audit:
            archive=writer.Writer(stream)
            minimum=maximum=None
            for index,(parent,children) in enumerate(groups()):
                minimum=parent[0] if minimum is None else min(minimum,parent[0])
                maximum=parent[0] if maximum is None else max(maximum,parent[0])
                inputs=[(x%factor,y%factor,raw) for (z,x,y),raw in children]
                raw, counts=aggregate_tiles(inputs,factor)
                archive.write_tile(zxy_to_tileid(*parent),gzip.compress(raw,compresslevel=6,mtime=0))
                audit.write(json.dumps({'zxy':parent,'logical_zoom':parent[0]+offset,'children':[zxy for zxy,_ in children],**counts})+'\n')
                if index%1000==0: print(f'{target.stem}: aggregate {index} blocks',flush=True)
            metadata=reader.metadata(); metadata['experiment']={'variant':f'aggregated{factor*factor}',
                'standard_sha256':sha256(standard),'aggregation':'exact-protobuf-multiset-v1'}
            if minimum is None:raise ValueError('No applicable Standard zoom for aggregation')
            output_header={**header,'tile_compression':Compression.GZIP,'min_zoom':minimum,
                'max_zoom':maximum,'center_zoom':max(0,header['center_zoom']-offset)}
            archive.finalize(output_header,metadata)
        partial.replace(target); evidence_partial.replace(evidence)
    receipt.write_text(json.dumps({'inputs':identity,'archive_sha256':sha256(target),
        'evidence_sha256':sha256(evidence)},indent=2)+'\n',encoding='utf-8')
    return target


def convert_archive(mvt, variant, *, force=False):
    """Commit both format outputs, loss/normalization diagnostics and measurements."""
    mvt=Path(mvt); stem=mvt.name.removesuffix('_mvt.pmtiles')
    outputs=[mvt.with_name(stem+'_'+fmt+'.pmtiles') for fmt in FORMATS[1:]]
    measurements=mvt.with_suffix('.measurements.jsonl.gz')
    manifest=mvt.with_suffix('.experiment.json')
    build=json.loads((cli_path().parent/'mlt-build.json').read_text())
    identity={'schema':1,'mvt_sha256':sha256(mvt),'build':build,'budget_mib':int(os.environ.get('MLT_DECODE_MEMORY_MIB','256'))}
    if not force and manifest.exists() and measurements.exists() and all(p.exists() for p in outputs):
        old=json.loads(manifest.read_text())
        if old.get('inputs')==identity and all(sha256(p)==old['archives'][p.name]['sha256'] for p in outputs):
            print(f'Up to date: {stem}',flush=True); return old
    started=time.perf_counter(); tiles=unique=roundtrip_differences=0; cache=OrderedDict(); cache_bytes=0
    payload_counts={}; source_ids=set(); feature_count=vertex_count=0
    with ExitStack() as stack:
        handle=stack.enter_context(mvt.open('rb')); source=MmapSource(handle); reader=Reader(source); header=reader.header()
        metadata=reader.metadata(); compression=header['tile_compression']
        streams=[stack.enter_context(p.with_suffix('.pmtiles.partial').open('wb')) for p in outputs]
        archives=[writer.Writer(s) for s in streams]
        audit=stack.enter_context(gzip.open(measurements.with_suffix('.gz.partial'),'wt',encoding='utf-8'))
        encoder=stack.enter_context(RustEncoder())
        seen=set()
        for zxy,payload in all_tiles(source):
            raw=raw_payload(payload,compression); key=hashlib.sha256(raw).hexdigest()
            if key in cache:
                encoded,stats=cache.pop(key); cache[key]=(encoded,stats)
            else:
                encoded,stats=encoder.encode(raw)
                cache[key]=(encoded,stats); cache_bytes+=sum(map(len,encoded))+len(raw)
                while cache_bytes>16*1024*1024 and len(cache)>1:
                    _,(old_encoded,_)=cache.popitem(last=False)
                    cache_bytes-=sum(map(len,old_encoded)) # conservative cap; raw bytes overcount only
            compressed=[gzip.compress(b,compresslevel=6,mtime=0) for b in encoded]
            tileid=zxy_to_tileid(*zxy)
            for archive,payload_mlt in zip(archives,compressed): archive.write_tile(tileid,payload_mlt)
            record={'kind':'address','zxy':zxy,'logical_zoom':zxy[0]+VARIANTS[variant],'payload_key':key,
                'stored_mvt_bytes':len(payload)}
            audit.write(json.dumps(record,separators=(',',':'))+'\n')
            if key not in seen:
                seen.add(key); unique+=1
                content=content_summary(raw)
                payload_counts[key]=(sum(l['feature_instances'] for l in content),sum(l['vertices'] for l in content))
                source_ids.update(i for l in content for i,_ in l['source_ids'])
                rows=[]
                for version,(b,gz,stat) in enumerate(zip(encoded,compressed,stats),1):
                    differences=stat['roundtrip_differences']; roundtrip_differences+=len(differences)
                    rows.append({'format':'mltv'+str(version),'raw_bytes':len(b),'gzip_bytes':len(gz),
                        'payload_sha256':hashlib.sha256(gz).hexdigest(),**stat})
                audit.write(json.dumps({'kind':'payload','payload_key':key,'mvt_raw_bytes':len(raw),
                    'mvt_gzip_bytes':len(gzip.compress(raw,compresslevel=6,mtime=0)),
                    'content':content,'formats':rows},separators=(',',':'))+'\n')
            n_features,n_vertices=payload_counts[key]
            feature_count+=n_features;vertex_count+=n_vertices
            tiles+=1
            if tiles%500==0: print(f'{stem}: {tiles} addresses, {unique} MVT payloads, {time.perf_counter()-started:.1f}s',flush=True)
        for version,archive in enumerate(archives,1):
            archive.finalize({**header,'tile_type':TileType.MLT,'tile_compression':Compression.GZIP},
                {**metadata,'format':'mlt','experiment':{'variant':variant,'mlt_version':version,'encoder':build}})
    for p in outputs: p.with_suffix('.pmtiles.partial').replace(p)
    measurements.with_suffix('.gz.partial').replace(measurements)
    result={'inputs':identity,'tile_count':tiles,'unique_mvt_payloads':unique,
        'feature_count':feature_count,'vertex_count':vertex_count,'unique_source_features':len(source_ids),
        'roundtrip_differing_layers':roundtrip_differences,'elapsed_seconds':time.perf_counter()-started,
        'archives':{p.name:{'sha256':sha256(p),'file_bytes':p.stat().st_size} for p in [mvt,*outputs]},
        'measurements_sha256':sha256(measurements)}
    manifest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(f'Written: {stem}: {tiles} addresses; {roundtrip_differences} differing layer round trips',flush=True)
    return result


def extend_dataset(name, output, *, force=False, selected_variants=None):
    output=Path(output)
    standard=output/f'{name}_standard_mvt.pmtiles'
    conversions={}
    for variant in (selected_variants or VARIANTS):
        offset=VARIANTS[variant]
        mvt=output/f'{name}_{variant}_mvt.pmtiles'
        if variant.startswith('aggregated'):
            aggregate_archive(standard,mvt,offset,force=force)
        result=convert_archive(mvt,variant,force=force)
        for fmt in FORMATS:
            filename=f'{name}_{variant}_{fmt}.pmtiles';info=result['archives'][filename]
            conversions[variant+'_'+fmt]={'filename':filename,'size_bytes':info['file_bytes'],
                'archive_sha256':info['sha256'],'tile_count':result['tile_count'],
                'feature_count':result.get('feature_count'),'vertex_count':result.get('vertex_count'),
                'unique_source_features':result.get('unique_source_features'),
                'exit_code':0,'time_seconds':result['elapsed_seconds'],'compression':'gzip',
                'extent':4096*2**offset,'detail_offset':offset,
                'encoder':result['inputs']['build'] if fmt!='mvt' else 'GDAL/provenance',
                'validation':{'passed':result['roundtrip_differing_layers']==0,'mode':'native-roundtrip',
                    'normalizations':'MVT importer column unification; polygon winding; integer widths',
                    'roundtrip_differing_layers':result['roundtrip_differing_layers']}}
    return conversions
