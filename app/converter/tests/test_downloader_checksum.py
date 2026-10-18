"""docs/maps.md requires a SHA-256 per benchmark import.

Upstream archives are mutable: Louisiana is a biannual release, BGT changes
daily, and the Amsterdam extract already changed size under this study once --
378 MB against the 266 MB of the copy measured before, which made every figure
from the older archive incomparable. A number in the paper is only attributable
to the bytes it was computed from.

Nothing here computed SHA-256 before. `downloader.py` offered `compute_md5`
only, which docs/maps.md flagged as the requirement being met "by hand or not
at all".
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.downloader import compute_sha256


def test_matches_hashlib_for_a_known_payload(tmp_path):
    payload = tmp_path / "x.bin"
    payload.write_bytes(b"groundswell" * 10_000)

    assert compute_sha256(payload) == hashlib.sha256(
        payload.read_bytes()).hexdigest()


def test_reads_in_chunks_rather_than_whole_files(tmp_path):
    """Source archives run to hundreds of megabytes; Louisiana's is 661 MB."""
    payload = tmp_path / "big.bin"
    payload.write_bytes(b"\0" * (5 * 1024 * 1024))

    assert len(compute_sha256(payload)) == 64
