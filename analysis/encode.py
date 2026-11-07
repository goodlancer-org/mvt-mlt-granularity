"""Encode completed provenance MVT with the pinned host Rust CLI.

Useful while Docker generates subsequent pyramids: ``python -m analysis.encode
--workers 2 --wait``. Every variant uses the same host build for both versions.
"""
from concurrent.futures import ProcessPoolExecutor
import argparse
import json
import shutil
from pathlib import Path
import time
from .pipeline import ROOT,registry
from .extended import VARIANTS


def encode_variant(dataset,variant,force):
    from app.converter.src.extended_tiles import extend_dataset
    return extend_dataset(dataset,ROOT/'app/data/output',force=force,selected_variants=[variant])


def write_protocols(datasets=None):
    output=ROOT/'app/data/output';target=ROOT/'app/data/protocols';target.mkdir(parents=True,exist_ok=True)
    for d in registry():
        name=d['id']
        if datasets and name not in datasets:continue
        formats={};validation={};standard=None
        for variant in VARIANTS:
            r=json.loads((output/f'{name}_{variant}_mvt.experiment.json').read_text())
            if variant=='standard':standard=r
            for fmt in ('mvt','mltv1','mltv2'):
                filename=f'{name}_{variant}_{fmt}.pmtiles';info=r['archives'][filename]
                formats[variant+'_'+fmt]={'path':filename,'archive_bytes':info['file_bytes'],
                    'archive_sha256':info['sha256'],'tile_count':r['tile_count'],
                    'generation_method':'exact_aggregation' if variant.startswith('aggregated') else 'gdal_provenance',
                    'encoder':r['inputs']['build'] if fmt!='mvt' else 'GDAL 3.13.3'}
                validation[variant+'_'+fmt]={'passed':r['roundtrip_differing_layers']==0,
                    'scope':'Rust-imported layer; type unification, integer widths and polygon winding normalized'}
        formats['mvt']=dict(formats['standard_mvt']);formats['mlt']=dict(formats['standard_mltv1'])
        result={'version':'2.1','dataset':{'id':name,'name':name,'title':d['display_name']},
            'experiment':'extended-granularity-v1','outputs':formats,'validation':validation,
            'source_provenance':f'provenance/{name}.provenance.sqlite',
            'topology':{'feature_instance_count':standard['feature_count'],
                'logical_feature_count':standard['unique_source_features'],'vertex_count':standard['vertex_count']}}
        canonical=target/(name+'.json')
        history=output.parent/'historical/python-0.2.2/protocols'/canonical.name
        if canonical.exists() and not history.exists():
            history.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(canonical,history)
        text=json.dumps(result,indent=2)+'\n'
        (target/(name+'.extended.json')).write_text(text,encoding='utf-8')
        canonical.write_text(text,encoding='utf-8')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,default=1)
    parser.add_argument('--wait',action='store_true')
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--dataset',action='append')
    parser.add_argument('--protocols-only',action='store_true')
    args=parser.parse_args(argv)
    if args.protocols_only:write_protocols(args.dataset);return 0
    if not 1<=args.workers<=8:parser.error('workers must be 1..8')
    pending={(d['id'],v) for d in registry() if not args.dataset or d['id'] in args.dataset for v in VARIANTS}
    running={};completed={}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        while pending or running:
            for future,key in list(running.items()):
                if future.done():
                    completed.update(future.result());del running[future]
                    print('Completed:',*key,flush=True)
            for dataset,variant in sorted(pending):
                if len(running)>=args.workers:break
                base='standard' if variant.startswith('aggregated') else variant
                generation=ROOT/'app/data/output'/f'{dataset}_{base}_mvt.generation.json'
                if not generation.exists():continue
                value=json.loads(generation.read_text())
                if value.get('inputs',{}).get('provenance_method')!='materialized-global-fid-v1':continue
                future=pool.submit(encode_variant,dataset,variant,args.force)
                running[future]=(dataset,variant);pending.remove((dataset,variant))
                print('Encoding:',dataset,variant,flush=True)
            if pending and not running and not args.wait:
                raise FileNotFoundError('Generate provenance MVT first, or use --wait: '+str(sorted(pending)))
            if pending or running:time.sleep(2)
    write_protocols(args.dataset)
    return 0

if __name__=='__main__':raise SystemExit(main())
