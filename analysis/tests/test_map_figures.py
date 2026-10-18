"""Exercise real MVT/PMTiles decoding, fallback selection and generated artifacts."""
import gzip
import json
import unittest
import copy
import math
import yaml
from pathlib import Path
from analysis.tests.test_pipeline import fixture_directory

import mapbox_vector_tile
from pmtiles.reader import Reader
from pmtiles.writer import Writer
from pmtiles.tile import Compression, TileType, zxy_to_tileid

from analysis.map_figures import discover, generate, read_tile, load_regions, DEFAULT_REGIONS
from analysis.map_styles.osm_fig import category


class MapFiguresTest(unittest.TestCase):
    def archive(self, path, compression):
        with path.open('wb') as handle:
            writer = Writer(handle)
            # A north-west triangle makes axis reversal/extent mistakes detectable.
            for z, extent in ((2,4096),(3,8192),(4,4096)):
                payload = mapbox_vector_tile.encode({'name':'water', 'features':[
                    {'geometry': {'type':'Polygon', 'coordinates': [[[0,0],[extent,0],[0,extent],[0,0]]]},
                     'properties': {'natural':'water'}}]},
                    default_options={'extents':extent, 'y_coord_down':True})
                writer.write_tile(zxy_to_tileid(z, 0, 0), gzip.compress(payload) if compression == Compression.GZIP else payload)
            writer.finalize({'tile_type':TileType.MVT, 'tile_compression':compression},
                            {'vector_layers':[{'id':'water', 'minzoom':2}]})

    def test_discovery_ignores_other_variants_and_scratch(self):
        with fixture_directory() as directory:
            root = Path(directory)
            for name in ('tiny_standard_mvt.pmtiles','tiny_standard_mlt.pmtiles',
                         'tiny_dense4_mvt.pmtiles','tiny_standard_water.group.tmp.pmtiles'):
                (root/name).touch()
            self.assertEqual([p.name for p in discover(root)], ['tiny_standard_mvt.pmtiles'])

    def test_real_decode_preserves_orientation_and_normalizes_extent(self):
        for compression in (Compression.NONE, Compression.GZIP):
            with self.subTest(compression=compression), fixture_directory() as directory:
                path = Path(directory)/'tiny_standard_mvt.pmtiles'
                self.archive(path, compression)
                with path.open('rb') as handle:
                    reader = Reader(lambda o,n: (handle.seek(o), handle.read(n))[1])
                    geom, props = read_tile(reader, (3,0,0))['water'][0]
                    self.assertEqual(geom.bounds, (0,0,4096,4096))
                    self.assertTrue(geom.covers(__import__('shapely').Point(50,50)))
                    self.assertFalse(geom.covers(__import__('shapely').Point(4000,4000)))
                    with self.assertRaisesRegex(RuntimeError, 'Missing tile'):
                        read_tile(reader, (3,1,1))

    def test_unknown_map_generates_three_nested_panels_and_latex(self):
        with fixture_directory() as directory:
            root = Path(directory)
            self.archive(root/'tiny_standard_mvt.pmtiles', Compression.GZIP)
            output = root/'figures'
            records = generate(root, output, dpi=40)
            self.assertEqual([p['z'] for p in records[0]['panels']], [2,3,4])
            self.assertEqual(len(list(output.glob('map_tiny_z*.png'))), 3)
            self.assertEqual(len(list(output.glob('map_tiny_z*.pdf'))), 3)
            latex = (output/'map_samples.tex').read_text()
            self.assertIn('magenta outlines', latex)
            self.assertEqual(latex.count(r'\begin{figure*}'), 1)
            self.assertIn('map_tiny_z4.pdf', latex)
            self.assertEqual(json.loads((output/'map_samples.json').read_text())['format'], 'MVT')

    def test_curated_zooms_and_matched_louisiana_views(self):
        regions = load_regions()
        expected = {'natural_earth_vector':[5,7,9],
                    'pdok_netherlands_infrostructure':[12,13,14],
                    'usfws_luisiana_wetlands_geopackage':[10,12,14],
                    'swisstopo_mountains_vector':[10,12,14], 'louisiana-260912':[10,12,14]}
        for stem, zooms in expected.items():
            self.assertEqual([p['z'] for p in regions[stem]['panels']],zooms)
        for osm,nwi in zip(regions['louisiana-260912']['panels'],regions['usfws_luisiana_wetlands_geopackage']['panels']):
            for key in ('z','x','y','view_bounds'):
                self.assertEqual(osm[key],nwi[key])

    def test_yaml_rejects_out_of_bounds_and_non_square_views(self):
        original = yaml.safe_load(DEFAULT_REGIONS.read_text(encoding='utf-8'))
        for change in ('outside', 'nonsquare'):
            with self.subTest(change=change), fixture_directory() as directory:
                config=copy.deepcopy(original)
                panel=config['datasets']['natural_earth_vector']['panels'][0]
                if change=='outside':
                    panel['view_bounds'][0]=panel['level_bounds'][0]-1
                else:
                    panel['view_bounds'][0]+=.1
                path=Path(directory)/'regions.yaml'
                path.write_text(yaml.safe_dump(config),encoding='utf-8')
                with self.assertRaises(RuntimeError):load_regions(path)

    def test_custom_yaml_is_used_and_recorded(self):
        with fixture_directory() as directory:
            root=Path(directory)
            self.archive(root/'tiny_standard_mvt.pmtiles',Compression.GZIP)
            panels=[]
            for z in (2,3,4):
                # Interior crop avoids the archive's default +-85 degree bound.
                n=2**z
                # Align top-left crops so that each finer view stays nested.
                top=.01
                bottom=top+.5/n
                west=-180+.01*360
                east=west+.5/n*360
                north=math.degrees(math.atan(math.sinh(math.pi*(1-2*top))))
                south=math.degrees(math.atan(math.sinh(math.pi*(1-2*bottom))))
                panels.append(dict(z=z,x=0,y=0,view_bounds=[west,south,east,north],
                                   level_bounds=[-180,-85,180,85]))
            path=root/'regions.yaml'
            path.write_text(yaml.safe_dump({'version':1,'datasets':{'tiny':{'region':'Custom area','panels':panels}}}),encoding='utf-8')
            records=generate(root,root/'figures',dpi=40,regions_file=path)
            self.assertEqual(records[0]['panels'][0]['view_bounds'],panels[0]['view_bounds'])
            self.assertIn('Custom area',(root/'figures/map_samples.tex').read_text())
            manifest=json.loads((root/'figures/map_samples.json').read_text())
            self.assertEqual(len(manifest['regions_sha256']),64)

    def test_osm_classifies_tags_even_in_buildings_layer(self):
        self.assertEqual(category('buildings', {'natural':'wetland'}), 'Wetland')
        self.assertEqual(category('buildings', {'natural':'water'}), 'Water')
        self.assertEqual(category('buildings', {'building':'yes'}), 'Buildings')
        self.assertEqual(category('buildings', {'other_tags':'"highway"=>"primary"'}), 'Roads and routes')


if __name__ == '__main__':
    unittest.main()
