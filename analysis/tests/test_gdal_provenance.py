"""Native GDAL regression; run in the converter Docker image, host skips without GDAL."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('osgeo'),'GDAL bindings are tested in the converter container')
class ProvenanceTest(unittest.TestCase):
    def test_disjoint_source_ids_and_exact_cells_and_rtree(self):
        from osgeo import ogr,osr
        from app.converter.src.feature_provenance import prepare_provenance
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'tiny.gpkg'
            srs=osr.SpatialReference();srs.ImportFromEPSG(3857)
            db=ogr.GetDriverByName('GPKG').CreateDataSource(str(source))
            for name,ids in [('first',[1,3]),('second',[1,2,3,5])]:
                layer=db.CreateLayer(name,srs,ogr.wkbPoint)
                layer.CreateField(ogr.FieldDefn('label',ogr.OFTString))
                for fid in ids:
                    f=ogr.Feature(layer.GetLayerDefn());f.SetFID(fid);f['label']=f'{name}/{fid}'
                    point=ogr.Geometry(ogr.wkbPoint);point.AddPoint_2D(float(fid),10.)
                    f.SetGeometry(point);self.assertEqual(layer.CreateFeature(f),0)
            db=None
            with patch.dict(os.environ,{'MLT_EXPERIMENT_SCRATCH':str(root/'scratch')}):
                derived,lookup=prepare_provenance(source,root/'export')
            with sqlite3.connect(source) as original,sqlite3.connect(derived) as actual,sqlite3.connect(lookup) as ids:
                mapped=ids.execute('SELECT id,source_layer,source_fid FROM feature_provenance').fetchall()
                self.assertEqual(len({r[0] for r in mapped}),6)
                for global_id,layer,local_id in mapped:
                    self.assertEqual(original.execute(f'SELECT geom,label FROM "{layer}" WHERE fid=?',(local_id,)).fetchone(),
                                     actual.execute(f'SELECT geom,label FROM "{layer}" WHERE fid=?',(global_id,)).fetchone())
                self.assertEqual(actual.execute('SELECT id FROM rtree_second_geom ORDER BY id').fetchall(),[(5,),(6,),(7,),(9,)])
            original.close();actual.close();ids.close()
            db=ogr.Open(str(derived));self.assertEqual(db.GetLayerByName('second').GetFeature(9)['label'],'second/5');db=None

if __name__=='__main__':unittest.main()
