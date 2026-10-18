"""What happens when a source reads back as having no layers.

On 2026-08-29 the Amsterdam GeoPackage was finalised at 18:07:28 and the
conversion job opened it at 18:07:37. Both readers failed on those nine-second-old
bytes -- `ogrinfo -json -so` in the analyser, and `PRAGMA foreign_key_check`
inside Planetiler -- and both succeeded on the same file later. The data
directory was inside a Syncthing share on a Windows bind mount, so a 1.7 GB file
that had just appeared was being hashed and re-read underneath the pipeline.

Two things follow, and this module fixes both.

An analysis that finds no layers is not yet a verdict, so it is taken again.

And when it stays empty the job must stop. `generate_vector_profile` answers an
empty layer list with a single catch-all layer that declares no attributes at
all; the 18:07 run produced exactly that, and the one conversion that completed
encoded 30 BGT featuretypes as one attribute-less layer. A study whose claim is
that MLT beats MVT by encoding attributes columnar cannot report a size measured
from a tile set with no attributes in it -- and nothing downstream would have
shown it, because the archive looks perfectly healthy.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analyzer import confirm_layers


class Reader:
    """Stands in for analyze_source, returning a prepared sequence of answers."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, source_path):
        self.calls += 1
        answer = self.answers[min(self.calls - 1, len(self.answers) - 1)]
        return {"file": "amsterdam.gpkg", "size_bytes": 1690873856, "layers": answer}


def test_an_analysis_that_found_no_layers_is_read_again():
    """The first read of a just-written GeoPackage is not trusted on its own."""
    reader = Reader([{"name": "bgt_pand", "fields": []}])
    slept = []

    confirmed = confirm_layers(
        {"layers": []}, "/data/sources/amsterdam/amsterdam.gpkg",
        analyse=reader, sleep=slept.append,
    )

    assert [layer["name"] for layer in confirmed["layers"]] == ["bgt_pand"]
    assert reader.calls == 1
    assert slept, "a re-read that follows a failed one should wait first"


def test_an_analysis_that_already_has_layers_is_not_read_again():
    """The retry is for the empty case only; a good analysis costs nothing."""
    reader = Reader([{"name": "never_used", "fields": []}])

    confirmed = confirm_layers(
        {"layers": [{"name": "bgt_pand", "fields": []}]}, "/s/amsterdam.gpkg",
        analyse=reader, sleep=lambda _: None,
    )

    assert [layer["name"] for layer in confirmed["layers"]] == ["bgt_pand"]
    assert reader.calls == 0


def test_a_source_that_never_reports_layers_is_refused():
    """Better a failed job than a protocol full of attribute-less figures."""
    reader = Reader([])

    with pytest.raises(RuntimeError, match="no layers"):
        confirm_layers(
            {"layers": []}, "/data/sources/amsterdam/amsterdam.gpkg",
            analyse=reader, attempts=3, sleep=lambda _: None,
        )

    assert reader.calls == 2, "the analysis in hand counts as the first attempt"


