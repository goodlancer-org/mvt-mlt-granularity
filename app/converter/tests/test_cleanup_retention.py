"""Tests for what the conversion pipeline deletes once it finishes.

Sources were previously deleted unconditionally, so re-running a dataset meant
re-downloading it (630 MB for the Louisiana wetlands). Layer stats sidecars are
the raw evidence behind the per-layer metrics, so they are worth keeping too.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.convert import cleanup_targets

SOURCES = Path("/data/sources/la_geodatabase_wetlands")
SIDECARS = [
    Path("/data/output/la_mvt.pmtiles.layerstats.tsv.gz"),
    Path("/data/output/la_mlt.pmtiles.layerstats.tsv.gz"),
]


def test_keeps_everything_when_retention_is_on():
    assert cleanup_targets(
        SOURCES, SIDECARS, keep_sources=True, keep_layerstats=True
    ) == []


def test_removes_sources_when_source_retention_is_off():
    assert cleanup_targets(
        SOURCES, SIDECARS, keep_sources=False, keep_layerstats=True
    ) == [SOURCES]


def test_removes_layerstats_when_layerstats_retention_is_off():
    assert cleanup_targets(
        SOURCES, SIDECARS, keep_sources=True, keep_layerstats=False
    ) == SIDECARS


def test_removes_both_when_all_retention_is_off():
    assert cleanup_targets(
        SOURCES, SIDECARS, keep_sources=False, keep_layerstats=False
    ) == [SOURCES, *SIDECARS]


def test_tolerates_a_dataset_with_no_sources_directory():
    assert cleanup_targets(
        None, SIDECARS, keep_sources=False, keep_layerstats=True
    ) == []
