"""Conversions must not overlap.

conversion_time_ms and peak_memory_mb are reported results, not logs. The
import endpoint starts a thread per request, so two datasets submitted close
together would run Planetiler twice at once and contend for CPU and memory --
silently corrupting both metrics for both datasets.
"""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api import conversion_slot


def _record_slot_usage(label, log, lock):
    with conversion_slot():
        with lock:
            log.append(f"{label}:enter")
        time.sleep(0.05)
        with lock:
            log.append(f"{label}:exit")


def test_two_conversions_never_overlap():
    log, lock = [], threading.Lock()
    threads = [
        threading.Thread(target=_record_slot_usage, args=(name, log, lock))
        for name in ("first", "second")
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    # Whichever wins the race, one must fully finish before the other starts.
    assert len(log) == 4
    assert log[0].endswith(":enter")
    assert log[1] == log[0].replace(":enter", ":exit")
    assert log[2].endswith(":enter")
    assert log[3] == log[2].replace(":enter", ":exit")


def test_the_slot_is_released_when_a_conversion_fails():
    try:
        with conversion_slot():
            raise RuntimeError("conversion blew up")
    except RuntimeError:
        pass

    # A leaked lock would deadlock every later import.
    acquired = []
    worker = threading.Thread(target=lambda: _acquire_into(acquired))
    worker.start()
    worker.join(timeout=5)

    assert acquired == ["got it"]


def _acquire_into(out):
    with conversion_slot():
        out.append("got it")
