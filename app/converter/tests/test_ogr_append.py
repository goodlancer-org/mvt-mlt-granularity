"""How the strict/tolerant retry differs between one-layer and many-into-one.

CityGML converts one member into one layer, so a half-written layer is best
discarded with -overwrite. The Groundswell merge appends 112 countries into a
single layer, where -overwrite on the 60th country would throw away the 59
already merged. The cleanup strategy is therefore the caller's choice.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ogr_append import append_attempts


def test_the_merge_retry_can_be_told_not_to_drop_the_layer():
    """Groundswell appends 112 countries into ONE layer. -overwrite on a retry
    would discard every country already merged, so the merge opts out."""
    _, retry = append_attempts(
        "/s/out.gpkg", "/s/AFG.gpkg", "groundswell",
        gpkg_exists=True, retry_replaces_layer=False,
    )

    assert "-overwrite" not in retry
    assert "-append" in retry
    assert "-skipfailures" in retry


def test_the_citygml_retry_still_replaces_its_layer():
    """One member is one layer there, so replacing it is the correct cleanup."""
    _, retry = append_attempts(
        "/s/out.gpkg", "/s/bgt.gml", "bgt_wegdeel", gpkg_exists=True,
    )

    assert "-overwrite" in retry
    assert "-append" not in retry
