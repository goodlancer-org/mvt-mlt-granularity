"""Scientific invariants: exact typed multisets, real Rust v1/v2 and additive SQL."""
from contextlib import ExitStack
import gzip
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import mapbox_vector_tile
from pmtiles.writer import Writer
from pmtiles.tile import Compression,TileType,zxy_to_tileid
from app.converter.src.mvt_aggregate import aggregate_tiles,tile_message,translated_commands
from app.converter.src.extended_tiles import RustEncoder,extend_dataset
from analysis import extended
from analysis.tests.test_pipeline import fixture_directory


def raw_tile(extent=4096):
    return mapbox_vector_tile.encode({'name':'mixed','features':[
        {'id':11,'geometry':{'type':'LineString','coordinates':[[-30,10],[2000,50],[4200,100]]},'properties':{'mixed':1,'bool':True,'name':'repeat'}},
        {'id':12,'geometry':{'type':'Point','coordinates':[40,80]},'properties':{'mixed':'one','bool':False,'name':'repeat'}},
        {'id':11,'geometry':{'type':'Point','coordinates':[2000,50]},'properties':{'mixed':2.5,'bool':True,'name':'repeat'}}]},
        default_options={'y_coord_down':True,'extents':extent})


class ExtendedTest(unittest.TestCase):
    def test_rust_budget_reaches_mvt_input_decoder(self):
        tile=tile_message(raw_tile());layer=tile.layers[0]
        template=type(layer.features[1])();template.CopyFrom(layer.features[1])
        layer.ClearField('features')
        for i in range(20000):
            feature=layer.features.add();feature.CopyFrom(template);feature.id=i
        raw=tile.SerializeToString(deterministic=True)
        with patch.dict(os.environ,{'MLT_DECODE_MEMORY_MIB':'1'}):
            with RustEncoder() as encoder:
                with self.assertRaisesRegex(RuntimeError,'MVT error:.*element memory limit exceeded'):
                    encoder.encode(raw)
        with patch.dict(os.environ,{'MLT_DECODE_MEMORY_MIB':'256'}):
            with RustEncoder() as encoder:_,stats=encoder.encode(raw)
            self.assertTrue(all(not s['roundtrip_differences'] for s in stats))

    def test_multiset_keeps_ids_types_duplicates_fragments_and_buffers(self):
        raw=raw_tile()
        aggregate,counts=aggregate_tiles([(0,0,raw),(1,1,raw)],2)
        self.assertEqual(counts['features'],6)
        self.assertEqual(counts['vertices'],10)
        layer=tile_message(aggregate).layers[0]
        self.assertEqual(layer.extent,8192)
        self.assertEqual(len(layer.keys),len(set(layer.keys)))
        self.assertEqual(len(layer.values),len(tile_message(raw).layers[0].values))
        self.assertEqual([f.id for f in layer.features],[11,12,11]*2)
        self.assertEqual(set(v.ListFields()[0][0].name for v in layer.values),
                         {'int_value','double_value','string_value','bool_value'})
        self.assertEqual(list(layer.features[3].geometry),translated_commands(tile_message(raw).layers[0].features[0].geometry,4096,4096))

    def test_aggregation_rejects_wrong_extent(self):
        with self.assertRaisesRegex(ValueError,'extent'):aggregate_tiles([(0,0,raw_tile(8192))],2)

    def test_rust_roundtrip_and_version_tags(self):
        with RustEncoder() as encoder:
            outputs,stats=encoder.encode(raw_tile())
        self.assertNotEqual(outputs[0],outputs[1])
        for data,stat in zip(outputs,stats):
            self.assertEqual(stat['roundtrip_differences'],[])
            self.assertEqual(sum(l['frame_bytes'] for l in stat['layers']),len(data))
            self.assertLessEqual(sum(s['payload_bytes'] for s in stat['streams']),len(data))

    def test_full_fixture_pipeline_exact_multisets_and_decomposition(self):
        base=extended.ROOT/'temp';base.mkdir(exist_ok=True)
        with fixture_directory() as folder:
            root=Path(folder);output=root/'app/data/output';output.mkdir(parents=True)
            data=root/'docs/data';data.mkdir(parents=True);store=data/'extended'
            for variant,offset in [('standard',0),('dense4',1),('dense16',2)]:
                with (output/f'test_{variant}_mvt.pmtiles').open('wb') as f:
                    writer=Writer(f)
                    coords=[(4,x,y) for x in range(4) for y in range(4)] if variant=='standard' else [(4-offset,0,0)]
                    for zxy in sorted(coords,key=lambda p:zxy_to_tileid(*p)):
                        writer.write_tile(zxy_to_tileid(*zxy),gzip.compress(raw_tile(4096*2**offset),mtime=0))
                    writer.finalize({'tile_type':TileType.MVT,'tile_compression':Compression.GZIP},{})
            extend_dataset('test',output)
            with patch.object(extended,'ROOT',root),patch.object(extended,'DATA',data):
                for variant in extended.VARIANTS:extended.ingest_one('test',variant,store)
                db=extended.statistics(store)
            import sqlite3
            with sqlite3.connect(db) as con:
                rows=con.execute('SELECT aggregation_reduction_bytes+regeneration_reduction_bytes,total_reduction_bytes FROM decomposition').fetchall()
                self.assertEqual(len(rows),12)
                self.assertTrue(all(a==b for a,b in rows))
                self.assertEqual(con.execute('SELECT DISTINCT typeof(standard_bytes) FROM decomposition').fetchall(),[('integer',)])
                self.assertEqual(con.execute('SELECT MIN(passed),COUNT(*) FROM aggregation_validation').fetchone(),(1,2))
                self.assertEqual(con.execute('SELECT SUM(differing_addresses) FROM validation_summary').fetchone()[0],0)
                self.assertEqual(con.execute("SELECT unique_source_features FROM content_summary WHERE variant='standard'").fetchone()[0],2)
            con.close()

if __name__=='__main__':unittest.main()
