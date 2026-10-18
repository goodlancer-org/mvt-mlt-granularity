"""Tests for the per-layer metrics derived from Planetiler's layer stats.

The protocol already records per-layer sizes for every format, but nothing
reported them, so the study could only compare whole archives. Per layer, the
comparison is more interesting: on the Louisiana wetlands MLT is consistently
*larger* than MVT uncompressed, while the MLT archive is smaller -- columnar
encoding costs raw bytes and wins them back under compression.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.protocol import compute_layer_metrics

# Figures taken from the real Louisiana NWI protocol.
LOUISIANA = {
    "mvt_pmtiles": {"layers": {
        "Louisiana": {"size_bytes": 8_843_737, "tile_count": 47_135},
        "LA_Wetlands_Project_Metadata": {"size_bytes": 29_434_798, "tile_count": 46_434},
    }},
    "mlt_pmtiles": {"layers": {
        "Louisiana": {"size_bytes": 11_530_204, "tile_count": 47_135},
        "LA_Wetlands_Project_Metadata": {"size_bytes": 34_816_958, "tile_count": 46_434},
    }},
}


def test_counts_the_layers():
    assert compute_layer_metrics(LOUISIANA)["layer_count"] == 2


def test_reports_negative_savings_where_mlt_is_larger():
    layers = compute_layer_metrics(LOUISIANA)["layers"]

    # 8,843,737 -> 11,530,204 is a 30.4% increase, i.e. -30.4% "savings".
    assert layers["Louisiana"]["mlt_savings_pct"] == -30.38


def test_reports_each_layers_share_of_the_encoded_bytes():
    layers = compute_layer_metrics(LOUISIANA)["layers"]

    # 8,843,737 of 38,278,535 MVT bytes.
    assert layers["Louisiana"]["size_share"]["mvt"] == 23.1
    assert layers["LA_Wetlands_Project_Metadata"]["size_share"]["mvt"] == 76.9


def test_keeps_both_encodings_sizes_for_each_layer():
    layers = compute_layer_metrics(LOUISIANA)["layers"]

    assert layers["Louisiana"]["size_bytes"] == {"mvt": 8_843_737, "mlt": 11_530_204}


def test_falls_back_to_mbtiles_when_only_it_was_produced():
    conversions = {
        "mvt_mbtiles": {"layers": {"roads": {"size_bytes": 1000, "tile_count": 4}}},
        "mlt_mbtiles": {"layers": {"roads": {"size_bytes": 800, "tile_count": 4}}},
    }

    assert compute_layer_metrics(conversions)["layers"]["roads"]["mlt_savings_pct"] == 20.0


def test_returns_empty_when_no_layer_stats_were_captured():
    assert compute_layer_metrics({"mvt_pmtiles": {"layers": {}}}) == {
        "layer_count": 0, "layers": {}, "layers_without_tiles": [],
    }


def test_skips_savings_for_a_layer_present_in_only_one_encoding():
    conversions = {
        "mvt_pmtiles": {"layers": {"roads": {"size_bytes": 1000, "tile_count": 4}}},
        "mlt_pmtiles": {"layers": {}},
    }

    assert compute_layer_metrics(conversions)["layers"]["roads"]["mlt_savings_pct"] is None


# Planetiler reports attribute *volume* (how many keys and values a layer
# encodes), not distinct-value cardinality. These are what MLT's dictionary
# encoding acts on, and the richest available signal for why it wins or loses
# on a given layer.
WITH_ATTRIBUTES = {
    "mvt_pmtiles": {"layers": {
        "buildings": {
            "size_bytes": 1000, "tile_count": 4, "feature_count": 50,
            "attribute_keys": 30, "attribute_values": 500,
        },
    }},
    "mlt_pmtiles": {"layers": {
        "buildings": {
            "size_bytes": 800, "tile_count": 4, "feature_count": 50,
            "attribute_keys": 30, "attribute_values": 500,
        },
    }},
}


def test_carries_attribute_volume_through():
    layer = compute_layer_metrics(WITH_ATTRIBUTES)["layers"]["buildings"]

    assert layer["attribute_keys"] == 30
    assert layer["attribute_values"] == 500


def test_derives_attributes_per_feature():
    layer = compute_layer_metrics(WITH_ATTRIBUTES)["layers"]["buildings"]

    assert layer["attributes_per_feature"] == 10.0


def test_attributes_per_feature_is_none_without_a_feature_count():
    conversions = {
        "mvt_pmtiles": {"layers": {"roads": {"size_bytes": 10, "feature_count": 0,
                                             "attribute_values": 7}}},
    }

    assert compute_layer_metrics(conversions)["layers"]["roads"]["attributes_per_feature"] is None
