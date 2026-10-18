"""Real encoder/SQLite smoke tests for the three measurement stages and SQL."""
import gzip
import json
import sqlite3
import shutil
import uuid
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import patch

import mapbox_vector_tile
import maplibre_tiles
from pmtiles.writer import Writer
from pmtiles.tile import Compression, TileType

from analysis import pipeline, output_analysis_core as core


@contextmanager
def fixture_directory():
    base = (pipeline.ROOT / 'temp').resolve()
    root = base / ('analysis-test-' + uuid.uuid4().hex)
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        if root.resolve().parent != base:
            raise RuntimeError('Fixture cleanup escaped workspace temp directory')
        shutil.rmtree(root)


class PipelineTest(unittest.TestCase):
    def test_real_pairs_and_statistics(self):
        import geopandas as gpd
        from shapely.geometry import Point
        with fixture_directory() as temporary:
            root=Path(temporary)
            data=root/'docs/data';data.mkdir(parents=True)
            output=root/'app/data/output';output.mkdir(parents=True)
            source=root/'tiny.gpkg'
            gpd.GeoDataFrame({'id':[1,2]},geometry=[Point(0,0),Point(1,1)],crs=3857).to_file(source,layer='places',driver='GPKG')
            profile=root/'tiny.yaml'
            profile.write_text('tile_layers:\n- id: places\n  source_layers: [places]\noutput:\n  bounds: [-1, -1, 1, 1]\n')
            datasets=[dict(id='tiny',display_name='Tiny',source='tiny.gpkg',normalized='tiny.gpkg',profile='tiny.yaml')]
            raw=mapbox_vector_tile.encode({'name':'places','features':[
                {'geometry':{'type':'Point','coordinates':[i,i]},'properties':{'active':i%2==0,'name':'test'*30},'id':i} for i in range(100)]})
            mlt=maplibre_tiles.encode_mvt(raw)
            for variant in ('standard','dense4','dense16'):
                extent={'standard':4096,'dense4':8192,'dense16':16384}[variant]
                variant_raw=mapbox_vector_tile.encode({'name':'places','features':[
                    {'geometry':{'type':'Point','coordinates':[i,i]},'properties':{'active':i%2==0,'name':'test'*30},'id':i} for i in range(100)]},default_options={'extents':extent})
                for fmt,payload in [('mvt',variant_raw),('mlt',maplibre_tiles.encode_mvt(variant_raw))]:
                    with (output/f'tiny_{variant}_{fmt}.pmtiles').open('wb') as handle:
                        writer=Writer(handle)
                        for tileid in (1,2):writer.write_tile(tileid,gzip.compress(payload,compresslevel=0,mtime=17))
                        writer.finalize({'tile_type':TileType.MVT if fmt=='mvt' else TileType(6),'tile_compression':Compression.GZIP},{})
            with patch.object(pipeline,'ROOT',root),patch.object(pipeline,'DATA',data),patch.object(pipeline,'registry',return_value=datasets):
                for stage in ('sources','normalized'):
                    pipeline.profile(stage,pipeline.stage_output(stage))
                with closing(sqlite3.connect(pipeline.stage_output('sources'))) as con:
                    self.assertEqual(con.execute('SELECT stage FROM dataset_files').fetchone()[0],'raw')
                target=pipeline.stage_output('tiles')
                result=core.build_analysis_database(output,target,progress=None)
                self.assertEqual(result.maps,3)
                self.assertEqual(result.errors,0)
                pipeline.tile_extras(target,codec_sensitivity=True)
                from analysis.audit import build
                build(pipeline.stage_output('audit'),root,data,datasets,workers=1)
                with closing(sqlite3.connect(target)) as con:
                    rows=con.execute('SELECT raw_payload_bytes,gzip_payload_bytes,stored_bytes FROM tiles t JOIN archives a ON a.id=t.archive_id JOIN maps m ON m.id=a.map_id WHERE a.format=\'MVT\' AND m.variant=\'standard\'').fetchall()
                    self.assertTrue(all(r[0]==len(raw) and r[1]==len(gzip.compress(raw,compresslevel=6,mtime=0)) for r in rows))
                    self.assertTrue(any(r[1]!=r[2] for r in rows))
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM mlt_layers').fetchone()[0],3)
                    self.assertEqual(con.execute("SELECT SUM(feature_occurrences) FROM properties WHERE property_key='active'").fetchone()[0],600)
                    self.assertEqual(con.execute("SELECT SUM(distinct_values_capped) FROM properties WHERE property_key='active'").fetchone()[0],6)
                from analysis.attribute_types import build as build_types
                build_types(pipeline.stage_output('types'), root, datasets)
                pipeline.statistics(pipeline.stage_output('stats'))
                with closing(sqlite3.connect(pipeline.stage_output('stats'))) as con:
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM variant_summary').fetchone()[0],3)
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM granularity_gain').fetchone()[0],2)
                    self.assertEqual(con.execute('SELECT features FROM normalized_structure').fetchone()[0],2)
                    self.assertEqual(con.execute('SELECT bounds_ok FROM study_area').fetchone()[0],1)
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM codec_gain').fetchone()[0],3)
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM validation').fetchone()[0],3)
                    self.assertEqual(con.execute('SELECT SUM(address_count) FROM attribute_payload_pairs').fetchone()[0],6)
                    self.assertEqual(con.execute('SELECT SUM(value_occurrences) FROM attribute_type_summary').fetchone()[0],1200)
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM attribute_type_errors').fetchone()[0],0)
                    pipeline.describe(con,'stats',[])
                    con.commit()
                    self.assertEqual(con.execute("SELECT value FROM main.meta WHERE key='schema_name'").fetchone()[0],'results')
                    self.assertEqual(con.execute("SELECT value FROM main.meta WHERE key='schema_version'").fetchone()[0],'1')
                from analysis import report
                with patch.object(report,'ROOT',root),patch.object(report,'DATA',data),patch.object(report,'TABLES',root/'tables'),patch.object(report,'FIGURES',root/'figures'),patch.object(report,'registry',return_value=datasets):
                    report.report()
                    self.assertTrue((root/'tables/analysis_compression.tex').exists())
                    self.assertTrue((root/'tables/analysis_attribute_types.tex').exists())
                    self.assertTrue((data/'attribute_transitions.csv').exists())
                    article = root/'tables'
                    self.assertIn('Tiny & 0 & 1 & 2 & 1 &', (article/'paper_sources_rows.tex').read_text())
                    self.assertIn(' & 1 & 2 & 2 & 1', (article/'paper_normalized_rows.tex').read_text())
                    self.assertEqual((article/'paper_bytes_per_vertex_rows.tex').read_text().count(' \\\\'), 3)
                    with closing(sqlite3.connect(pipeline.stage_output('stats'))) as con:
                        structural = con.execute("SELECT 100*r_struct FROM stream_summary WHERE variant='standard'").fetchone()[0]
                    self.assertIn(f'{structural:.2f}', (article/'paper_streams_rows.tex').read_text())
                    self.assertTrue((root/'figures/analysis_sample_tiny.pdf').exists())
                    self.assertTrue((root/'figures/analysis_zoom_aligned.pdf').exists())
                    panels = (root/'figures/analysis_sample_panels.tex').read_text()
                    self.assertIn('figures/analysis_sample_tiny.pdf', panels)
                    self.assertIn('$z=1$, $x=0$, $y=0$', panels)
                    self.assertIn('Tiny', panels)
                    # Type/content differences remain diagnostic, not a report failure.
                    with closing(sqlite3.connect(pipeline.stage_output('stats'))) as con,con:
                        con.execute("UPDATE validation SET mismatches=1,passed=0,status='fail'")
                    report.report()
                    self.assertIn('DIAGNOSTIC: strict decoded equality: 3 differing addresses', (data/'claims_report.md').read_text())
                    with closing(sqlite3.connect(pipeline.stage_output('stats'))) as con,con:
                        con.execute('UPDATE study_area SET bounds_ok=0')
                    with self.assertRaisesRegex(RuntimeError,'Declared study bounds'):
                        report.report()
                    self.assertIn('FAIL: Declared study bounds',(data/'claims_report.md').read_text())

    def test_bad_frame_fails(self):
        with self.assertRaises((ValueError,EOFError)):
            core._parse_mlt_payload(b'\x7f\x01')

    def test_unnamed_arrow_geometry(self):
        import geopandas as gpd
        from shapely.geometry import Point
        from analysis.map_analysis_core import rebuild_analysis
        with fixture_directory() as root:
            source=root/'points.shp'
            gpd.GeoDataFrame({'id':[1,2]},geometry=[Point(0,0),Point(1,1)],crs=4326).to_file(source)
            database=root/'stats.sqlite'
            rebuild_analysis(root,database,files=[source])
            with closing(sqlite3.connect(database)) as con:
                self.assertEqual(con.execute('SELECT vertexCount FROM layers').fetchone()[0],2)


if __name__=='__main__':unittest.main()
