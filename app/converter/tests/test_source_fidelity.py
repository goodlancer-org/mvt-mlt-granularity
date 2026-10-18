"""What the pipeline discards, and whether it says so.

Audited 2026-08-30 by comparing each source against its output rather than by
trusting any signal the pipeline emitted. It converts the geometry the paper
describes in every case. What it did badly was discard quietly, in three
places, and one of the three moves layer_count -- which is one of the paper's
eighteen metrics, so a layer that disappears in silence is a wrong figure and
not merely untidiness.
"""

import json
import sqlite3
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.citygml_handler import layer_feature_counts
from src.convert import _extract_zip_source, choose_zip_member
from src.protocol import compute_layer_metrics


# The Saentis archive holds GPKG/de/078_Saentis.gpkg and GPKG/fr/078_Saentis.gpkg
# -- the German and French editions of one sheet, 28 layers each with identical
# structure. Selection took the first match in zipfile.namelist() order, so
# German won by packing order alone. Repacked the other way the study would
# convert French attribute values with the same layer and feature counts: no
# figure in any protocol or in results.md would change, and nothing downstream
# could detect it.
class TestChoosingTheSourceMember:
    SAENTIS = ["GPKG/de/078_Saentis.gpkg", "GPKG/fr/078_Saentis.gpkg", "readme.txt"]

    def test_the_chosen_member_does_not_depend_on_archive_ordering(self):
        forwards, _ = choose_zip_member(self.SAENTIS)
        backwards, _ = choose_zip_member(list(reversed(self.SAENTIS)))

        assert forwards == backwards

    def test_the_rejected_editions_are_reported_alongside_the_choice(self):
        chosen, alternatives = choose_zip_member(self.SAENTIS)

        assert chosen == "GPKG/de/078_Saentis.gpkg"
        assert alternatives == ["GPKG/fr/078_Saentis.gpkg"]

    def test_an_ordinary_single_file_archive_reports_no_alternatives(self):
        chosen, alternatives = choose_zip_member(["data/wetlands.gpkg"])

        assert chosen == "data/wetlands.gpkg"
        assert alternatives == []

    def test_format_priority_still_beats_alphabetical_order(self):
        """A .gpkg is preferred over a .shp however the two sort."""
        chosen, alternatives = choose_zip_member(["a/aaa.shp", "z/zzz.gpkg"])

        assert chosen == "z/zzz.gpkg"
        assert alternatives == []

    def test_an_archive_with_nothing_geospatial_chooses_nothing(self):
        assert choose_zip_member(["readme.txt"]) == (None, [])

    def test_shapefile_archives_prefer_the_largest_member(self, tmp_path):
        archive = tmp_path / "swisstopo.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("Data/Shapefiles/STRUCTHELV_BORDER.shp", b"x" * 32)
            zf.writestr("Data/Shapefiles/STRUCTHELV_LINE_AUX.shp", b"x" * 4096)
            zf.writestr("Data/Shapefiles/STRUCTHELV_LINE_AUX.dbf", b"dbf")
            zf.writestr("Data/Shapefiles/STRUCTHELV_LINE_AUX.shx", b"shx")

        extracted_path, chosen_member, alternatives = _extract_zip_source(archive, tmp_path / "out")

        assert chosen_member == "Data/Shapefiles/STRUCTHELV_LINE_AUX.shp"
        assert alternatives[0] == "Data/Shapefiles/STRUCTHELV_BORDER.shp"
        assert extracted_path is not None
        assert extracted_path.exists()


# Saentis' generated profile declares 28 layers and the tiles carry 27.
# Alluvial_and_Lacustrine_Structures_L is absent and nothing anywhere says it
# went missing or why.
class TestLayersThatProducedNoTiles:
    CONVERSIONS = {
        "mvt_pmtiles": {"layers": {"roads": {"size_bytes": 10, "feature_count": 5}}},
        "mlt_pmtiles": {"layers": {"roads": {"size_bytes": 9, "feature_count": 5}}},
    }

    def test_a_declared_layer_that_produced_no_tiles_is_named(self):
        metrics = compute_layer_metrics(
            self.CONVERSIONS, declared_layers=["roads", "alluvial_structures_l"])

        assert metrics["layers_without_tiles"] == ["alluvial_structures_l"]

    def test_layer_count_still_counts_the_layers_that_have_tiles(self):
        metrics = compute_layer_metrics(
            self.CONVERSIONS, declared_layers=["roads", "alluvial_structures_l"])

        assert metrics["layer_count"] == 1

    def test_nothing_is_claimed_missing_when_the_source_is_not_known(self):
        """UI imports do not always have a declared layer list to compare against."""
        metrics = compute_layer_metrics(self.CONVERSIONS)

        assert metrics["layers_without_tiles"] == []


# The Amsterdam extract is requested across 35 BGT featuretypes and yields 30.
# PDOK returns buurt, openbareruimte, stadsdeel, waterschap and wijk as
# 388-byte GML envelopes with no features. Dropping them is right; dropping
# them in silence means a member truncated by a failed download looks exactly
# like one that is legitimately empty.
class TestSourceMembersThatContributedNothing:
    def _gpkg(self, tmp_path, layers):
        path = tmp_path / "amsterdam.gpkg"
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE gpkg_contents (table_name TEXT, data_type TEXT)")
        for name, rows in layers.items():
            db.execute("INSERT INTO gpkg_contents VALUES (?, 'features')", (name,))
            db.execute(f'CREATE TABLE "{name}" (fid INTEGER PRIMARY KEY)')
            db.executemany(f'INSERT INTO "{name}" (fid) VALUES (?)',
                           [(i,) for i in range(rows)])
        db.commit()
        db.close()
        return path

    def test_counts_the_features_each_member_contributed(self, tmp_path):
        path = self._gpkg(tmp_path, {"bgt_pand": 3, "bgt_wegdeel": 7})

        assert layer_feature_counts(path) == {"bgt_pand": 3, "bgt_wegdeel": 7}

    def test_a_member_that_produced_an_empty_layer_counts_zero(self, tmp_path):
        path = self._gpkg(tmp_path, {"bgt_pand": 3, "buurt": 0})

        assert layer_feature_counts(path)["buurt"] == 0

    def test_a_member_that_produced_no_layer_at_all_is_absent(self, tmp_path):
        path = self._gpkg(tmp_path, {"bgt_pand": 3})

        assert "wijk" not in layer_feature_counts(path)


# conversion_time_ms times the tile-generation step alone. The paper defines it
# as "total time required to convert a source dataset into the target tile
# archive", and the download, archive extraction, CityGML merge and
# file-geodatabase normalisation all fall outside it. Preparation happens once
# per dataset and conversion four times, so a single number cannot both include
# preparation and stay per-format -- it is recorded separately instead, and the
# paper's definition is corrected in docs/paper-changes.md section 12.
class TestWhatThePreparationCostWasNotCounted:
    ANALYSIS = {"size_bytes": 10, "driver": "GPKG", "layers": []}
    CONVERSIONS = {"mvt_pmtiles": {"size_bytes": 10, "time_seconds": 1.0,
                                   "tile_count": 1, "exit_code": 0, "layers": {}}}

    def _protocol(self, tmp_path, **dataset):
        from src.protocol import generate_protocol
        path = generate_protocol(
            {"name": "saentis", "url": "x.zip", "format": "gpkg", **dataset},
            self.ANALYSIS, self.CONVERSIONS, tmp_path)
        return json.loads(Path(path).read_text(encoding="utf-8"))["dataset"]

    def test_preparation_is_recorded_at_dataset_level_not_per_format(self, tmp_path):
        """It is not per-format and must not look like it is."""
        protocol = self._protocol(tmp_path, preparation_time_ms=94_000)

        assert protocol["preparation_time_ms"] == 94_000

    def test_a_dataset_that_needed_no_preparation_records_no_figure(self, tmp_path):
        """Amsterdam reuses a cached merge: absent, not quietly rendered as 0."""
        protocol = self._protocol(tmp_path, preparation_time_ms=None)

        assert "preparation_time_ms" not in protocol

    def test_the_converted_member_is_named_on_the_protocol(self, tmp_path):
        protocol = self._protocol(
            tmp_path,
            source_member="GPKG/de/078_Saentis.gpkg",
            source_member_alternatives=["GPKG/fr/078_Saentis.gpkg"])

        assert protocol["source_member"] == "GPKG/de/078_Saentis.gpkg"
        assert protocol["source_member_alternatives"] == ["GPKG/fr/078_Saentis.gpkg"]

    def test_source_members_that_contributed_nothing_are_named(self, tmp_path):
        protocol = self._protocol(
            tmp_path, source_members_without_features=["buurt", "wijk"])

        assert protocol["source_members_without_features"] == ["buurt", "wijk"]

    def test_an_ordinary_source_carries_none_of_these_keys(self, tmp_path):
        protocol = self._protocol(tmp_path)

        for key in ("source_member", "source_member_alternatives",
                    "source_members_without_features"):
            assert key not in protocol
