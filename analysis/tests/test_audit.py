"""Semantic regressions: order, typed values, geometry, IDs, missing addresses."""
from contextlib import closing
from pathlib import Path
import gzip
import json
import sqlite3
import unittest

import mapbox_vector_tile
import maplibre_tiles
from pmtiles.writer import Writer
from pmtiles.tile import Compression, TileType
from shapely.geometry import Polygon

from analysis.audit import Audit, decoded_tile, feature_key, tile_bounds, polygon_wire_signature, finalize_geometry_status, project_source_crs_fallback
from analysis.tests.test_pipeline import fixture_directory


def encode(features):
    return mapbox_vector_tile.encode({'name':'places','features':features})


def feature(value=1, identifier=7, x=10):
    return {'id':identifier,'properties':{'value':value},'geometry':{'type':'Point','coordinates':[x,20]}}


def archive(path, payload, fmt, addresses=(1,2)):
    with path.open('wb') as stream:
        writer=Writer(stream)
        for tileid in addresses: writer.write_tile(tileid,gzip.compress(payload,mtime=0))
        writer.finalize({'tile_type':TileType.MVT if fmt=='MVT' else TileType(6),
                         'tile_compression':Compression.GZIP}, {})


class AuditTest(unittest.TestCase):
    def test_undeclared_gml_crs_is_not_silently_assigned(self):
        with fixture_directory() as root:
            config=root/'app/converter/config.yaml';config.parent.mkdir(parents=True)
            config.write_text('citygml_fallback_source_srs: EPSG:4326\n')
            source=root/'source.gml';source.write_text('<FeatureCollection/>')
            audit=Audit(root/'audit.sqlite',root,root,[])
            try:
                audit.record('tiny','source','geometry',None,source,'measured native envelope',component='source.gml',layer='places',native=[4,52,5,53])
                audit.record('tiny','source','geometry',None,source,'source union')
                audit.record('tiny','normalized','geometry',[4.5,52.5,4.6,52.6],source,'normalized union')
                project_source_crs_fallback(audit.con,root)
                original=audit.con.execute("SELECT native_crs,min_lon FROM bounds WHERE stage='source' AND kind='geometry' AND layer_name='places'").fetchone()
                self.assertEqual(original,(None,None))
                projected=audit.con.execute("SELECT min_lon,min_lat,max_lon,max_lat,status,details_json FROM bounds WHERE kind='geometry_pipeline_crs' AND layer_name IS NULL").fetchone()
                self.assertEqual(projected[:5],(4,52,5,53,'projected_with_pipeline_crs'))
                self.assertEqual(json.loads(projected[5])['crs_used'],'EPSG:4326')
                self.assertEqual(audit.con.execute("SELECT status FROM bounds_checks WHERE check_name='normalized_within_source_pipeline_crs'").fetchone()[0],'pass')
            finally:audit.con.close()

    def test_zero_area_rings_remain_decoder_disagreements(self):
        from mapbox_vector_tile.Mapbox.vector_tile_pb2 import tile as Tile
        tile=Tile();layer=tile.layers.add();layer.name='terrain';layer.version=2;layer.extent=4096
        item=layer.features.add();item.id=7;item.type=3
        cursor=[0,0]
        commands=[]
        for ring in [[(0,0),(100,0),(0,100)],[(200,200),(201,201),(202,202)]]:
            for i,(x,y) in enumerate(ring):
                if i==0:commands.append(9)
                elif i==1:commands.append((len(ring)-1)*8+2)
                for axis,value in enumerate((x,y)):
                    delta=value-cursor[axis];commands.append((delta<<1)^(delta>>63));cursor[axis]=value
            commands.append(15)
        item.geometry.extend(commands)
        raw=tile.SerializeToString();mlt=maplibre_tiles.encode_mvt(raw)
        self.assertNotEqual(decoded_tile(raw,'MVT')[0],decoded_tile(mlt,'MLT')[0])
        # The wire diagnostic explains this case but must never make validation pass.
        self.assertEqual(polygon_wire_signature(raw,'MVT'),polygon_wire_signature(mlt,'MLT'))

    def test_typed_properties_and_geometry_multisets(self):
        raw=encode([feature(),feature(x=30),feature()])
        self.assertEqual(decoded_tile(raw,'MVT')[0],decoded_tile(maplibre_tiles.encode_mvt(raw),'MLT')[0])
        reordered=encode([feature(),feature(),feature(x=30)])
        self.assertEqual(decoded_tile(raw,'MVT')[0],decoded_tile(reordered,'MVT')[0])
        for changed in [feature(True),feature('1'),feature(identifier=8),feature(x=11)]:
            self.assertNotEqual(decoded_tile(encode([feature()]),'MVT')[0], decoded_tile(encode([changed]),'MVT')[0])
        self.assertNotEqual(decoded_tile(encode([feature(),feature()]),'MVT')[0],decoded_tile(encode([feature()]),'MVT')[0])
        a=Polygon([(0,0),(1,0),(1,1),(0,0)])
        b=Polygon([(1,1),(1,0),(0,0),(1,1)])
        self.assertEqual(feature_key(1,{},a),feature_key(1,{},b))

    def test_persisted_full_validation_detects_real_mismatches(self):
        cases=[('equal',[feature()],(1,2),False),
               ('attribute',[feature(True)],(1,2),True),
               ('id',[feature(identifier=8)],(1,2),True),
               ('geometry',[feature(x=11)],(1,2),True),
               ('missing',[feature()],(1,),True)]
        with fixture_directory() as root:
            output=root/'app/data/output';output.mkdir(parents=True)
            d={'id':'tiny','display_name':'Tiny'}
            for name, features, addresses, bad in cases:
                archive(output/'tiny_standard_mvt.pmtiles',encode([feature()]),'MVT')
                archive(output/'tiny_standard_mlt.pmtiles',maplibre_tiles.encode_mvt(encode(features)),'MLT',addresses)
                audit=Audit(root/f'{name}.sqlite',root,root,[d])
                try:
                    audit.pair(d,'standard')
                    row=audit.con.execute('SELECT passed,mismatches,errors,checked_tiles FROM validation').fetchone()
                    self.assertEqual(row[0],int(not bad),name)
                    self.assertEqual(row[2],0,name)
                    self.assertEqual(row[1]>0,bad,name)
                    if not bad: self.assertEqual(row[3],2)
                    self.assertTrue(audit.con.execute("SELECT COUNT(*) FROM bounds WHERE kind='geometry'").fetchone()[0])
                    if name=='attribute':
                        from analysis import output_analysis_core as core
                        from analysis.validation_examples import export_examples
                        from analysis import tile_store
                        with closing(tile_store.Connection()) as tiles:
                            schema='CREATE TABLE maps(id BIGINT,dataset_name TEXT,variant TEXT); CREATE TABLE archives(id BIGINT,map_id BIGINT,path TEXT,format TEXT); CREATE TABLE tiles(archive_id BIGINT,z BIGINT,x BIGINT,y BIGINT,content_offset BIGINT,stored_bytes BIGINT);'
                            tiles.executescript(schema)
                            tiles.execute('INSERT INTO maps VALUES (1,?,?)',('tiny','standard'))
                            for aid,fmt in enumerate(('MVT','MLT'),1):
                                path=output/f'tiny_standard_{fmt.lower()}.pmtiles'
                                tiles.execute('INSERT INTO archives VALUES (?,1,?,?)',(aid,str(path),fmt))
                                header=core.read_pmtiles_header(path)
                                with path.open('rb') as handle:
                                    for run in core._iter_tile_runs_from_handle(handle,header):
                                        for delta in range(run.run_length):
                                            tiles.execute('INSERT INTO tiles VALUES (?,?,?,?,?,?)',(aid,*core.tileid_to_zxy(run.tile_id+delta),run.offset,run.length))
                            tile_store.write(tiles,root/'tile_stats',schema)
                        export_examples(audit.con,root,root)
                        changes=json.loads((root/'validation_examples.json').read_text())['examples'][0]['attribute_examples'][0]['changes']
                        self.assertEqual(changes,[{'field':'value','mvt':{'type':'int','value':1},'mlt':{'type':'bool','value':True}}])
                finally: audit.con.close()

    def test_geometry_envelopes_and_unknown_reference(self):
        self.assertEqual(tile_bounds(1,0,0)[::2],[-180,0])
        with fixture_directory() as root:
            audit=Audit(root/'audit.sqlite',root,root,[])
            try:
                audit.containment('tiny','absent',[0,0,1,1],None)
                audit.containment('tiny','outside',[0,0,1,1.01],[0,0,1,1])
                rows=audit.con.execute('SELECT status,north_excess FROM bounds_checks ORDER BY rowid').fetchall()
                self.assertEqual(rows[0],('unknown',None))
                self.assertEqual(rows[1][0],'fail')
                self.assertAlmostEqual(rows[1][1],.01)
            finally: audit.con.close()

    def test_corrupt_payload_is_persisted_as_error(self):
        with fixture_directory() as root:
            output=root/'app/data/output';output.mkdir(parents=True)
            archive(output/'tiny_standard_mvt.pmtiles',encode([feature()]),'MVT')
            with (output/'tiny_standard_mlt.pmtiles').open('wb') as stream:
                writer=Writer(stream)
                writer.write_tile(1,gzip.compress(maplibre_tiles.encode_mvt(encode([feature()])),mtime=0))
                writer.write_tile(2,gzip.compress(b'\xff',mtime=0))
                writer.finalize({'tile_type':TileType(6),'tile_compression':Compression.GZIP},{})
            audit=Audit(root/'audit.sqlite',root,root,[])
            try:
                audit.pair({'id':'tiny'},'standard')
                self.assertEqual(audit.con.execute('SELECT passed,checked_tiles,errors FROM validation').fetchone(),(0,1,1))
                self.assertEqual(audit.con.execute("SELECT COUNT(*) FROM validation_issues WHERE category='decode_error'").fetchone()[0],1)
                finalize_geometry_status(audit.con)
                self.assertEqual(audit.con.execute("SELECT status FROM bounds WHERE kind='geometry' AND format='MLT' AND zoom=1").fetchone()[0],'partial')
                self.assertEqual(audit.con.execute("SELECT status FROM bounds WHERE kind='geometry' AND format='MVT' AND zoom=1").fetchone()[0],'measured')
            finally:audit.con.close()
            archive(output/'tiny_standard_mlt.pmtiles',b'\xff','MLT')
            audit=Audit(root/'all_missing.sqlite',root,root,[])
            try:
                audit.pair({'id':'tiny'},'standard')
                finalize_geometry_status(audit.con)
                self.assertEqual(audit.con.execute("SELECT status FROM bounds WHERE kind='geometry' AND format='MLT' AND zoom=1").fetchone()[0],'unknown')
                self.assertEqual(audit.con.execute('SELECT checked_tiles,errors FROM validation').fetchone(),(0,2))
            finally:audit.con.close()


if __name__=='__main__': unittest.main()
