"""How one CityGML member is handed to ogr2ogr.

`-skipfailures` makes GDAL override -gt to 1, so every feature gets its own
SQLite transaction and every commit fsyncs. Measured on bgt_ondersteunendwaterdeel
(33 MB of GML) into a GeoPackage already holding one 64 KB layer:

    append, -skipfailures                72 s
    append, no -skipfailures              1 s
    append, -skipfailures + SYNC OFF      3 s
    create, -skipfailures                 3 s

The penalty applies to -update -append but not to creation, which is why layer 1
of a BGT archive is fast and layers 2..35 are not. bgt_wegdeel is simply the
first member large enough for 72x to exceed the one-hour timeout.

So members are converted strictly first, and retried tolerantly only if that
fails -- which also means a dropped feature becomes a recorded event rather than
a silent one, and the paper's per-layer feature counts can be trusted.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ogr_append import append_attempts


def attempts(layer="bgt_wegdeel", srs=None, gpkg_exists=False):
    return append_attempts(
        "/scratch/out.gpkg", "/scratch/bgt_wegdeel.gml", layer,
        source_srs=srs, gpkg_exists=gpkg_exists,
    )


def test_the_first_attempt_does_not_skip_failures():
    """The whole point: -skipfailures costs 72x on every member after the first."""
    first, _ = attempts(gpkg_exists=True)

    assert "-skipfailures" not in first


def test_a_failed_member_is_retried_tolerantly():
    """One bad geometry must not cost a whole layer -- BGT has known bad features."""
    _, retry = attempts(gpkg_exists=True)

    assert "-skipfailures" in retry


def test_the_first_member_creates_the_geopackage():
    first, _ = attempts(gpkg_exists=False)

    assert "-update" not in first
    assert "-append" not in first


def test_later_members_are_appended():
    first, _ = attempts(gpkg_exists=True)

    assert "-update" in first
    assert "-append" in first


def test_the_retry_replaces_whatever_the_failed_attempt_left_behind():
    """A strict attempt that dies midway leaves a partial layer. Appending the
    tolerant retry onto it would double every feature written before the fault."""
    _, retry = attempts(gpkg_exists=True)

    assert "-overwrite" in retry
    assert "-append" not in retry


def test_a_member_declaring_no_srs_is_given_one():
    first, _ = attempts(srs="EPSG:28992", gpkg_exists=True)

    assert first[first.index("-s_srs") + 1] == "EPSG:28992"


def test_a_member_declaring_its_own_srs_is_left_alone():
    first, _ = attempts(srs=None, gpkg_exists=True)

    assert "-s_srs" not in first


def test_every_attempt_reprojects_to_wgs84_and_linearises():
    for cmd in attempts(gpkg_exists=True):
        assert cmd[cmd.index("-t_srs") + 1] == "EPSG:4326"
        assert cmd[cmd.index("-nlt") + 1] == "CONVERT_TO_LINEAR"


def test_the_layer_name_comes_from_the_member():
    first, _ = attempts(layer="bgt_pand", gpkg_exists=True)

    assert first[first.index("-nln") + 1] == "bgt_pand"


def test_the_tolerant_retry_does_not_pay_an_fsync_per_feature():
    """-skipfailures pins -gt to 1, so the retry commits once per feature. On the
    same 33 MB member that took 72 s, disabling synchronous writes brought it to
    3 s. The scratch GeoPackage is disposable and rebuilt from source whenever a
    run dies, so durability buys nothing here and costs 24x."""
    _, retry = attempts(gpkg_exists=True)

    assert retry[retry.index("--config") + 1:retry.index("--config") + 3] == \
        ["OGR_SQLITE_SYNCHRONOUS", "OFF"]


def test_the_strict_pass_keeps_synchronous_writes():
    """It is already fast, so there is nothing to buy and no reason to risk it."""
    first, _ = attempts(gpkg_exists=True)

    assert "--config" not in first
