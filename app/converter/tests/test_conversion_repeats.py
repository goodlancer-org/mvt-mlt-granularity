"""Aggregation of repeated conversions of one format.

A single Planetiler run is not a measurement. Nominally identical runs of the
same source at the same heap differed by 8-28% in wall time, which is larger
than the MLT-vs-MVT effect the study reports -- so conversion metrics are
repeated and reported as a median with spread, exactly as render metrics are.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.protocol import aggregate_conversion_runs, generate_protocol


def run(seconds, mem, exit_code=0, size=4_104_388):
    return {
        "filename": "geocover_mvt_pmtiles.pmtiles",
        "size_bytes": size,
        "tile_count": 154,
        "feature_count": 56_830,
        "time_seconds": seconds,
        "peak_memory_mb": mem,
        "exit_code": exit_code,
        "layers": {"Bedrock": {"size_bytes": 900}},
        "log_file": "geocover_mvt_pmtiles.log",
    }


def test_reports_the_median_of_the_runs():
    out = aggregate_conversion_runs([run(14.5, 700.0), run(13.1, 690.0), run(16.9, 710.0)])

    assert out["time_seconds"] == 14.5
    assert out["peak_memory_mb"] == 700.0
    assert out["runs"] == 3


def test_records_the_observed_spread():
    out = aggregate_conversion_runs([run(14.5, 700.0), run(13.1, 690.0), run(16.9, 710.0)])

    assert out["spread"]["time_seconds"] == {"min": 13.1, "max": 16.9}
    assert out["spread"]["peak_memory_mb"] == {"min": 690.0, "max": 710.0}


def test_deterministic_outputs_have_no_spread():
    # Archive size and tile count should not move between runs. A non-zero
    # spread here is the signal that something is nondeterministic.
    out = aggregate_conversion_runs([run(14.5, 700.0), run(13.1, 690.0)])

    assert out["size_bytes"] == 4_104_388
    assert out["spread"]["size_bytes"] == {"min": 4_104_388, "max": 4_104_388}


def test_non_numeric_fields_come_from_a_successful_run():
    out = aggregate_conversion_runs([run(14.5, 700.0), run(13.1, 690.0)])

    assert out["filename"] == "geocover_mvt_pmtiles.pmtiles"
    assert out["layers"] == {"Bedrock": {"size_bytes": 900}}


def test_one_failure_among_three_is_not_averaged_away():
    out = aggregate_conversion_runs([run(14.5, 700.0), run(13.1, 690.0, exit_code=1)])

    assert out["exit_code"] == 1
    # Only the run that succeeded describes how long a conversion takes.
    assert out["time_seconds"] == 14.5
    assert out["runs"] == 2


def test_a_single_run_still_aggregates():
    out = aggregate_conversion_runs([run(14.5, 700.0)])

    assert out["runs"] == 1
    assert out["time_seconds"] == 14.5
    assert out["spread"]["time_seconds"] == {"min": 14.5, "max": 14.5}


