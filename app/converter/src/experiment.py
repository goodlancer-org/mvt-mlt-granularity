"""Reproduce the extended experiment from existing normalized GeoPackages.

Run inside the GDAL container: python -m src.experiment --registry /repo/analysis/datasets.json
"""
from __future__ import annotations
import argparse
import fnmatch
import json
from pathlib import Path
import shutil
import subprocess
import time
import os
import yaml
from .feature_provenance import prepare_provenance
from .extended_tiles import extend_dataset, sha256
from .gdal_tiles import (_gdal_mvt_command, _layer_conf, _pmtiles_direct_translation_command,
                         DENSE_VARIANTS, DEFAULT_MAX_TILE_BYTES, DEFAULT_MAX_TILE_FEATURES)


def run_dataset(name, source, profile, output, logs, *, force=False, mvt_only=False):
    source,output,logs=Path(source),Path(output),Path(logs)
    output.mkdir(parents=True,exist_ok=True); logs.mkdir(parents=True,exist_ok=True)
    history=output.parent/'historical/python-0.2.2'; history.mkdir(parents=True,exist_ok=True)
    history_manifest=history/(name+'.json')
    if not history_manifest.exists():
        original={}
        for p in output.glob(name+'_*.pmtiles'):
            if p.stem.endswith(('_mvt','_mlt')):
                target=history/p.name
                if not target.exists(): shutil.copy2(p,target)
                original[p.name]={'sha256':sha256(target),'file_bytes':target.stat().st_size}
        history_manifest.write_text(json.dumps(original,indent=2)+'\n',encoding='utf-8')
    provenance=output.parent/'provenance'
    vrt,lookup=prepare_provenance(source,provenance)
    profile=dict(profile) if isinstance(profile,dict) else yaml.safe_load(Path(profile).read_text(encoding='utf-8'))
    from osgeo import ogr
    datasource=ogr.Open(str(vrt)); available=[l.GetName() for l in datasource]
    for layer in profile['tile_layers']:
        selected=set(layer.get('source_layers',[]))
        for pattern in layer.get('source_layer_prefixes',[]):
            selected.update(n for n in available if fnmatch.fnmatchcase(n,pattern))
        layer['source_layers']=[n for n in available if n in selected]
    config=profile.get('output',{}); bounds=','.join(map(str,config.get('bounds',[]))) or None
    for variant in DENSE_VARIANTS:
        key=variant['key']; target=output/f'{name}_{key}_mvt.pmtiles'; manifest=target.with_suffix('.generation.json')
        identity={'normalized_sha256':sha256(source),'provenance_sha256':sha256(lookup),
                  'provenance_method':'materialized-global-fid-v1',
                  'profile':profile,'variant':variant,'preserve_fid':True,
                  'gdal':subprocess.check_output(['ogrinfo','--version'],text=True).strip()}
        if not force and target.exists() and manifest.exists():
            old=json.loads(manifest.read_text())
            if old['inputs']==identity and old['sha256']==sha256(target):
                print(f'Up to date: {target.name}',flush=True); continue
        conf=_layer_conf(profile,{},variant['detail_offset'])
        conf={k:v for k,v in conf.items() if k in available}
        scratch=Path(os.environ.get('MLT_EXPERIMENT_SCRATCH','/tmp/mlt-experiment'))/name/'tiles'
        scratch.mkdir(parents=True,exist_ok=True)
        mbtiles=scratch/f'{name}_{key}.mbtiles'; temp=scratch/f'{name}_{key}.tiles.sqlite'
        mbtiles.unlink(missing_ok=True); temp.unlink(missing_ok=True)
        command=_gdal_mvt_command(source_path=vrt,output_mbtiles=mbtiles,min_zoom=int(config.get('min_zoom',0)),
            max_zoom=int(config.get('max_zoom',14)),bounds=bounds,variant=variant,
            source_layers=list(conf),layer_conf=conf,simplification=1.6,simplification_max_zoom=1.,
            max_size=DEFAULT_MAX_TILE_BYTES,max_features=DEFAULT_MAX_TILE_FEATURES,temporary_db=temp)
        command.insert(1,'-preserve_fid')
        started=time.perf_counter()
        print(f'Generating {name}/{key}, with source provenance IDs',flush=True)
        with (logs/f'{name}_{key}.extended-gdal.log').open('w',encoding='utf-8') as log:
            log.write(json.dumps(command)+'\n');log.flush()
            subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
            packed=scratch/(target.stem+'.pmtiles');packed.unlink(missing_ok=True)
            partial=target.with_name(target.stem+'.partial.pmtiles');partial.unlink(missing_ok=True)
            subprocess.run(_pmtiles_direct_translation_command(mbtiles,packed),check=True,stdout=log,stderr=subprocess.STDOUT)
        shutil.copyfile(packed,partial);partial.replace(target);packed.unlink();mbtiles.unlink();temp.unlink(missing_ok=True)
        manifest.write_text(json.dumps({'inputs':identity,'sha256':sha256(target),
            'elapsed_seconds':time.perf_counter()-started,'command':command},indent=2)+'\n',encoding='utf-8')
    if mvt_only:return {}
    conversions=extend_dataset(name,output,force=force)
    protocol={'version':'2.1','dataset':{'id':name,'name':name,'title':name,'extent':config.get('bounds')},
        'experiment':'extended-granularity-v1','source_provenance':str(lookup),
        'outputs':{key:{'path':v['filename'],'archive_bytes':v['size_bytes'],
            'archive_sha256':v['archive_sha256'],'tile_count':v['tile_count'],
            'generation_method':'exact_aggregation' if key.startswith('aggregated') else 'gdal_provenance_rust',
            'encoder':v['encoder']} for key,v in conversions.items()},
        'validation':{key:v['validation'] for key,v in conversions.items()}}
    protocol['outputs']['mvt']=dict(protocol['outputs']['standard_mvt'])
    protocol['outputs']['mlt']=dict(protocol['outputs']['standard_mltv1'])
    standard=conversions['standard_mvt']
    protocol['topology']={'feature_instance_count':standard['feature_count'],
        'logical_feature_count':standard['unique_source_features'],
        'vertex_count':standard['vertex_count']}
    (output.parent/'protocols').mkdir(parents=True,exist_ok=True)
    canonical=output.parent/'protocols'/f'{name}.json'
    old_protocol=history/'protocols'/canonical.name
    if canonical.exists() and not old_protocol.exists():
        old_protocol.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(canonical,old_protocol)
    text=json.dumps(protocol,indent=2)+'\n'
    (output.parent/'protocols'/f'{name}.extended.json').write_text(text,encoding='utf-8')
    canonical.write_text(text,encoding='utf-8')
    return conversions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--data',type=Path,default=Path('/data'))
    parser.add_argument('--dataset',action='append')
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--mvt-only',action='store_true',help='Prepare provenance and the three GDAL pyramids only')
    args=parser.parse_args()
    for d in json.loads(args.registry.read_text()):
        if args.dataset and d['id'] not in args.dataset: continue
        relative=Path(d['normalized']).relative_to('app/data')
        source=args.data/relative
        profile=args.data/Path(d['profile']).relative_to('app/data')
        run_dataset(d['id'],source,profile,args.data/'output',args.data/'logs',force=args.force,mvt_only=args.mvt_only)

if __name__=='__main__': main()
