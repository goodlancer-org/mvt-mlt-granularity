"""Wire-type distinctions and local column scope, independent of feature ordering."""
import unittest

import mapbox_vector_tile
import maplibre_tiles
from mapbox_vector_tile.Mapbox import vector_tile_pb2

from analysis.attribute_types import compare_profiles, mlt_columns, mvt_profiles


class AttributeTypesTest(unittest.TestCase):
    def test_exact_protobuf_types_and_absence(self):
        tile = vector_tile_pb2.tile()
        layer = tile.layers.add(name='test', version=2, extent=4096)
        layer.keys.append('value')
        for field, value in [('int_value', 1), ('uint_value', 1), ('sint_value', -1),
                             ('float_value', 1.5), ('double_value', 1.5),
                             ('bool_value', True), ('string_value', '1')]:
            setattr(layer.values.add(), field, value)
            layer.features.add().tags.extend([0, len(layer.values)-1])
        layer.features.add()  # absent, distinct from a bool false or numeric zero
        before = mvt_profiles(tile.SerializeToString())
        rows = compare_profiles(before, {'test': {'value': ('OptString', 1, 'Scalar')}})
        self.assertEqual({r[2] for r in rows}, {'int','uint','sint','float','double','bool','string'})
        self.assertEqual(sum(r[6] for r in rows), 7)
        self.assertTrue(all(r[7:10] == (8,1,7) for r in rows))
        self.assertEqual(sum(r[10] == 'to_string' for r in rows), 6)

    def test_actual_codec_layer_scope_and_shared_dictionary(self):
        def feature(value, i):
            return {'geometry': {'type': 'Point', 'coordinates': [i,i]},
                    'properties': {'value': value, 'name:en': 'hello', 'name:de': 'hallo'}}
        raw = mapbox_vector_tile.encode([
            {'name': 'mixed', 'features': [feature(1,0),feature('one',1)]},
            {'name': 'numeric', 'features': [feature(1,0),feature(2,1)]}])
        rows = compare_profiles(mvt_profiles(raw), mlt_columns(maplibre_tiles.encode_mvt(raw)))
        mixed = [r for r in rows if r[0]=='mixed' and r[1]=='value']
        numeric = [r for r in rows if r[0]=='numeric' and r[1]=='value']
        self.assertEqual({r[3].removeprefix('Opt') for r in mixed}, {'String'})
        self.assertTrue(all(r[9]==2 for r in mixed))
        self.assertTrue(all(r[10]=='numeric_representation' for r in numeric))
        self.assertEqual({r[1] for r in rows}, {'value','name:en','name:de'})

    def test_malformed_and_ambiguous_inputs(self):
        with self.assertRaises((ValueError, EOFError)):
            mlt_columns(b'\x7f\x01')
        tile = vector_tile_pb2.tile()
        for _ in range(2):
            tile.layers.add(name='duplicate', version=2)
        with self.assertRaisesRegex(ValueError, 'duplicate MVT layer'):
            mvt_profiles(tile.SerializeToString())
        rows = compare_profiles({'a': (1, {'x': {'int': 1}}, {'x': 1}, {})},
                                {'a': {'extra': ('String', 0, 'Scalar')}})
        self.assertEqual({r[10] for r in rows}, {'missing_mlt_column','mlt_only_column'})


if __name__ == '__main__':
    unittest.main()
