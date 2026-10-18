"""Export bounded, reproducible witnesses for failed full pair comparisons."""
from collections import defaultdict
from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3

from .audit import decoded_tile
from . import output_analysis_core as core


def display_value(value):
    if value is None: return {'absent':True}
    kind, text=value
    if kind=='int': parsed=int(text)
    elif kind=='bool': parsed=text=='True'
    elif kind=='null': parsed=None
    elif kind=='float':
        parsed=float.fromhex(text)
        if not math.isfinite(parsed): parsed=text
    else: parsed=text
    return {'type':kind,'value':parsed}


def export_examples(con, root, data):
    """One failed tile per dataset, up to five attribute witnesses, never a pass override."""
    examples=[]
    datasets=[r[0] for r in con.execute('SELECT DISTINCT dataset_id FROM validation WHERE passed=0 ORDER BY dataset_id')]
    with closing(sqlite3.connect((Path(data)/'tile_stats.sqlite').as_uri()+'?mode=ro',uri=True)) as tiles:
        for dataset in datasets:
            issue=con.execute("SELECT variant,z,x,y,layer_name,details_json FROM validation_issues WHERE dataset_id=? AND category='decoded_content' ORDER BY (variant='standard') DESC,z,x,y,layer_name LIMIT 1",(dataset,)).fetchone()
            if not issue: continue
            variant,z,x,y,layer,details=issue
            example={'dataset_id':dataset,'variant':variant,'z':z,'x':x,'y':y,'layer':layer,
                     'audit_details':json.loads(details),'attribute_examples':[]}
            try:
                decoded={}
                for fmt in ('MVT','MLT'):
                    path,offset,length=tiles.execute('''SELECT a.path,t.content_offset,t.stored_bytes FROM tiles t
                        JOIN archives a ON a.id=t.archive_id JOIN maps m ON m.id=a.map_id
                        WHERE m.dataset_name=? AND m.variant=? AND a.format=? AND z=? AND x=? AND y=?''',
                        (dataset,variant,fmt,z,x,y)).fetchone()
                    path=Path(path)
                    header=core.read_pmtiles_header(path)
                    with path.open('rb') as stream:
                        raw=core._decompress(core._read_section(stream,header.tile_data_offset+offset,length),header.tile_compression,str(path))
                    decoded[fmt]=decoded_tile(raw,fmt)[0][layer]
                    example[fmt.lower()+'_path']=path.relative_to(root).as_posix()
                left=decoded['MVT']-decoded['MLT'];right=decoded['MLT']-decoded['MVT']
                candidates=defaultdict(list)
                for feature in right:
                    candidates[feature[0],feature[2]].append(feature)
                for expected in left:
                    options=candidates.get((expected[0],expected[2]),[])
                    if not options: continue
                    expected_props=dict(expected[1])
                    def difference(actual):
                        actual_props=dict(actual[1])
                        return sum(expected_props.get(k)!=actual_props.get(k) for k in expected_props.keys()|actual_props.keys())
                    actual=min(options,key=difference)
                    actual_props=dict(actual[1])
                    changes=[{'field':k,'mvt':display_value(expected_props.get(k)),
                              'mlt':display_value(actual_props.get(k))}
                             for k in sorted(expected_props.keys()|actual_props.keys())
                             if expected_props.get(k)!=actual_props.get(k)]
                    if changes:
                        example['attribute_examples'].append({'feature_id':expected[0],
                            'association':'same normalized geometry and ID; closest typed property set',
                            'changes':changes[:10]})
                    if len(example['attribute_examples'])>=5: break
            except Exception as error:
                example['example_error']=f'{type(error).__name__}: {error}'
            examples.append(example)
    output={'sampling':'One persisted decoded-content discrepancy per dataset, preferring Standard; witnesses do not replace full counts or establish unique feature identity.',
            'examples':examples}
    (Path(data)/'validation_examples.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
