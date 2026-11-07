"""Exercise the real Rust allocation budget exposed by the binding patch."""
import json
import os
import unittest
from unittest.mock import patch
import mapbox_vector_tile
import maplibre_tiles
from analysis.mlt_codec import decode_mlt, memory_budget_bytes


class NativeMemoryBudgetTest(unittest.TestCase):
    def test_rust_budget_is_enforced_and_can_be_raised(self):
        raw = mapbox_vector_tile.encode({'name': 'places', 'features': [
            {'id': 7, 'geometry': {'type': 'Point', 'coordinates': [12, 34]},
             'properties': {'name': 'test'}}]})
        tile = maplibre_tiles.encode_mvt(raw)
        with self.assertRaisesRegex(ValueError, 'memory limit exceeded'):
            maplibre_tiles.decode_mlt(tile, max_memory_bytes=1)
        with self.assertRaisesRegex(ValueError, 'memory limit exceeded'):
            maplibre_tiles.decode_mlt_to_geojson(tile, max_memory_bytes=1)
        with patch.dict(os.environ, {'MLT_DECODE_MEMORY_MIB': '256'}):
            self.assertEqual(memory_budget_bytes(), 268435456)
            layer, = decode_mlt(tile)
        self.assertEqual(layer.name, 'places')
        self.assertEqual(layer.features[0].id, 7)
        self.assertEqual(dict(layer.features[0].properties), {'name': 'test'})
        self.assertTrue(json.loads(maplibre_tiles.decode_mlt_to_geojson(tile, max_memory_bytes=1048576)))

    def test_invalid_budget_is_rejected(self):
        for value in ('0', '-1', '4096', 'invalid'):
            with self.subTest(value=value), patch.dict(os.environ, {'MLT_DECODE_MEMORY_MIB': value}):
                with self.assertRaises(ValueError):
                    memory_budget_bytes()
