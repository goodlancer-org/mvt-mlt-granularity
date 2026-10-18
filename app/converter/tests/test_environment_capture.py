"""Tests for recording the conditions a conversion ran under.

conversion_time_ms and peak_memory_mb are reported results, so they only mean
something alongside the machine and settings that produced them. Two runs of
this project already differ: Louisiana was first converted with a 2 GB heap in
a 15.3 GB container, everything after with 16 GB in a 23.5 GB container.
Without this block the protocols look interchangeable when they are not.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.protocol import capture_environment

CFG = {
    "java_heap": "16g",
    "min_zoom": 0,
    "max_zoom": 14,
    "planetiler_jar": "/opt/planetiler.jar",
}


def test_records_the_settings_that_change_the_measurements():
    env = capture_environment(CFG, cpu_count=16, total_memory_bytes=25_246_105_600)

    assert env["java_heap"] == "16g"
    assert env["min_zoom"] == 0
    assert env["max_zoom"] == 14


def test_records_the_machine_the_numbers_came_from():
    env = capture_environment(CFG, cpu_count=16, total_memory_bytes=25_246_105_600)

    assert env["cpu_count"] == 16
    assert env["total_memory_bytes"] == 25_246_105_600


def test_stamps_when_the_conditions_were_captured():
    env = capture_environment(CFG, cpu_count=16, total_memory_bytes=1)

    # ISO-8601 with timezone, so protocol age is unambiguous across machines.
    assert env["captured_at"].endswith("+00:00")
    assert env["captured_at"].count("-") >= 2


def test_falls_back_to_the_running_machine_when_not_told():
    env = capture_environment(CFG)

    assert isinstance(env["cpu_count"], int) and env["cpu_count"] >= 1
    assert env["total_memory_bytes"] is None or env["total_memory_bytes"] > 0


def test_survives_a_config_missing_optional_keys():
    env = capture_environment({"java_heap": "8g"}, cpu_count=4, total_memory_bytes=1)

    assert env["java_heap"] == "8g"
    assert env["min_zoom"] is None
    assert env["max_zoom"] is None


def test_runtime_codec_versions_and_configuration_are_traceable():
    from importlib.metadata import version
    first = capture_environment({'max_zoom': 12})
    changed = capture_environment({'max_zoom': 13})
    assert first['mlt_transcoder'] == version('maplibre-tiles')
    assert first['mvt_codec'] == version('mapbox-vector-tile')
    assert first['config_sha256'] != changed['config_sha256']
