"""Process memory sampling and output-file size measurements."""
import threading
from pathlib import Path

try:
    import psutil as _psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


class PeakMemory:
    """The highest RSS observed for a process, sampled on its own clock.

    peak_memory_mb is a reported result, and the paper defines it as the maximum
    memory consumption observed during the conversion. Sampling used to happen
    once per line Planetiler wrote to stdout, so a phase that logged nothing was
    never sampled and any peak inside it was invisible.

    Memory that could not be read at all stays None rather than becoming 0.0,
    which would read as a measured figure.
    """

    def __init__(self, read_rss, interval=0.2):
        self._read_rss = read_rss
        self._interval = interval
        self._peak_bytes = None
        self._stop = threading.Event()
        self._thread = None

    def poll(self):
        """Take one sample. A process that has already exited is not an error."""
        try:
            rss = self._read_rss()
        except Exception:
            return
        if rss is None:
            return
        if self._peak_bytes is None or rss > self._peak_bytes:
            self._peak_bytes = rss

    @property
    def peak_mb(self):
        if self._peak_bytes is None:
            return None
        return round(self._peak_bytes / (1024 * 1024), 1)

    def start(self):
        if self._thread is not None:
            return

        def loop():
            while True:
                self.poll()
                if self._stop.wait(self._interval):
                    return

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop sampling and return the peak, so a caller can record it inline."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval * 5)
            self._thread = None
        return self.peak_mb


def _process_rss(pid):
    """Resident memory of a running process, or None if it cannot be read."""
    if not _PSUTIL_AVAILABLE:
        return None
    try:
        return _psutil.Process(pid).memory_info().rss
    except _psutil.Error:
        return None


def get_output_size(output_path):
    """Get file size for an output file, or 0 if it doesn't exist."""
    p = Path(output_path)
    return p.stat().st_size if p.exists() else 0


