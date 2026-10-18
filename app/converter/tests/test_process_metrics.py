"""Tests for how peak conversion memory is observed.

The paper defines peak_memory_mb as the maximum memory consumption observed
during the conversion process. Sampling driven by Planetiler's log output never
looks at a phase that logs nothing, so the maximum it reports is the maximum
over log events rather than over the run.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.process_metrics import PeakMemory

MB = 1024 * 1024


def test_peak_is_the_highest_sample_taken():
    readings = iter([100 * MB, 900 * MB, 200 * MB])
    peak = PeakMemory(lambda: next(readings))

    peak.poll()
    peak.poll()
    peak.poll()

    assert peak.peak_mb == 900.0


def test_memory_that_could_never_be_read_is_absent_rather_than_zero():
    """A missing psutil reported 0.0 MB, which reads as a measured figure."""
    peak = PeakMemory(lambda: None)

    peak.poll()

    assert peak.peak_mb is None


def test_a_process_that_exits_mid_sample_keeps_the_peak_it_reached():
    def reader():
        if calls:
            raise ProcessLookupError("process is gone")
        calls.append(1)
        return 700 * MB

    calls = []
    peak = PeakMemory(reader)

    peak.poll()
    peak.poll()

    assert peak.peak_mb == 700.0


def test_sampling_runs_on_its_own_clock_rather_than_on_log_output():
    readings = []

    peak = PeakMemory(lambda: readings.append(1) or 500 * MB, interval=0.005)
    peak.start()
    try:
        while len(readings) < 3:
            pass
    finally:
        peak.stop()

    assert peak.peak_mb == 500.0
    assert len(readings) >= 3
