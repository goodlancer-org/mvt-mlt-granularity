"""Acquiring Groundswell: discovery, unwrapping, schema and merge.

Everything here runs offline against a recorded CMR response. The collection
ships two representations of every country -- a GeoPackage and a file
geodatabase -- so the selection has to be exact: ingesting both would count
every country twice and double a dataset the paper reports feature counts for.
"""

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.groundswell_handler import EXPECTED_GRANULES, granule_urls_from_cmr_json

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "cmr_groundswell.json").read_text()
)


def test_selects_one_geopackage_archive_per_country():
    """The collection ships a GeoPackage AND a file geodatabase per country.
    Ingesting both would count every country twice."""
    urls = granule_urls_from_cmr_json(FIXTURE)

    assert len(urls) == EXPECTED_GRANULES == 112
    assert all(u.endswith("-gpkg.zip") for u in urls)


def test_returns_each_country_once():
    urls = granule_urls_from_cmr_json(FIXTURE)

    assert len(set(urls)) == len(urls)


# ── the count guard ──────────────────────────────────────────────────────

def test_a_short_granule_list_is_refused():
    """Method.md states 112 countries. A 111-country merge reported as
    Groundswell would understate the dataset with nothing in the output to
    show it."""
    from src.groundswell_handler import verify_granule_count

    try:
        verify_granule_count(["u"] * 111)
    except RuntimeError as exc:
        assert "111" in str(exc) and "112" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for a short granule list")


def test_the_expected_granule_list_is_accepted():
    from src.groundswell_handler import verify_granule_count

    verify_granule_count(["u"] * 112)


# ── unwrapping the nested archive ────────────────────────────────────────

def test_finds_the_geopackage_inside_its_same_named_directory(tmp_path):
    """The archive nests AFG.gpkg/AFG.gpkg. Matching the directory hands
    ogr2ogr a path it cannot open."""
    from src.groundswell_handler import country_gpkg_from_zip

    zip_path = tmp_path / "afg.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("AFG.gpkg/AFG.gpkg", b"SQLite format 3\x00stub")
        archive.writestr("documentation.pdf", b"%PDF-1.4 stub")
        archive.writestr("data-dictionary.xlsx", b"PK stub")

    found = country_gpkg_from_zip(zip_path, tmp_path / "out")

    assert found.is_file()
    assert found.name == "AFG.gpkg"
    assert found.read_bytes().startswith(b"SQLite format 3")


def test_an_archive_without_a_geopackage_is_refused(tmp_path):
    from src.groundswell_handler import country_gpkg_from_zip

    zip_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("documentation.pdf", b"%PDF-1.4 stub")

    try:
        country_gpkg_from_zip(zip_path, tmp_path / "out")
    except RuntimeError as exc:
        assert "no .gpkg" in str(exc).lower()
    else:
        raise AssertionError("expected RuntimeError for a GeoPackage-free archive")


# ── schema uniformity ────────────────────────────────────────────────────

def test_identical_schemas_are_accepted():
    from src.groundswell_handler import verify_uniform_schemas

    fields = [("NAME0", "String"), ("BL10", "Real")]
    verify_uniform_schemas({"AFG": fields, "MAR": list(fields)})


def test_a_country_with_an_extra_column_is_named():
    """Merging it would leave ~4,000 cells of nulls that read as real data."""
    from src.groundswell_handler import verify_uniform_schemas

    try:
        verify_uniform_schemas({
            "AFG": [("NAME0", "String"), ("BL10", "Real")],
            "MAR": [("NAME0", "String"), ("BL10", "Real"), ("EXTRA", "Real")],
        })
    except RuntimeError as exc:
        assert "MAR" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for a divergent schema")


def test_a_retyped_column_is_caught():
    from src.groundswell_handler import verify_uniform_schemas

    try:
        verify_uniform_schemas({
            "AFG": [("BL10", "Real")],
            "TZA": [("BL10", "String")],
        })
    except RuntimeError as exc:
        assert "TZA" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for a retyped column")


# ── credentials ──────────────────────────────────────────────────────────

def test_credentials_come_from_the_environment(monkeypatch):
    """They must never be written into the repository."""
    from src.groundswell_handler import earthdata_credentials

    monkeypatch.setenv("EDL_USERNAME", "someone")
    monkeypatch.setenv("EDL_PASSWORD", "secret")

    assert earthdata_credentials() == ("someone", "secret")


def test_missing_credentials_say_what_to_set(monkeypatch):
    from src.groundswell_handler import earthdata_credentials

    monkeypatch.delenv("EDL_USERNAME", raising=False)
    monkeypatch.delenv("EDL_PASSWORD", raising=False)

    try:
        earthdata_credentials()
    except RuntimeError as exc:
        assert "EDL_USERNAME" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when credentials are absent")


def test_credentials_are_detected_without_raising(monkeypatch):
    """The two sources of record disagree on whether the CloudFront redirect
    demands a token, so the download attaches one when it can and proceeds
    anonymously when it cannot. Neither path may raise on the way in."""
    from src.groundswell_handler import have_earthdata_credentials

    monkeypatch.delenv("EDL_USERNAME", raising=False)
    monkeypatch.delenv("EDL_PASSWORD", raising=False)
    assert have_earthdata_credentials() is False

    monkeypatch.setenv("EDL_USERNAME", "someone")
    monkeypatch.setenv("EDL_PASSWORD", "secret")
    assert have_earthdata_credentials() is True


# ── the merge ────────────────────────────────────────────────────────────

def test_the_first_country_creates_and_the_rest_append():
    from src.groundswell_handler import merge_commands_for

    first = merge_commands_for("/o.gpkg", "/AFG.gpkg", gpkg_exists=False)[0]
    later = merge_commands_for("/o.gpkg", "/MAR.gpkg", gpkg_exists=True)[0]

    assert "-update" not in first
    assert "-append" in later


def test_every_country_lands_in_one_named_layer():
    from src.groundswell_handler import MERGED_LAYER, merge_commands_for

    cmd = merge_commands_for("/o.gpkg", "/MAR.gpkg", gpkg_exists=True)[0]

    assert cmd[cmd.index("-nln") + 1] == MERGED_LAYER == "groundswell"


def test_a_failed_country_is_retried_without_discarding_the_merge():
    """-overwrite here would throw away every country already merged."""
    from src.groundswell_handler import merge_commands_for

    retry = merge_commands_for("/o.gpkg", "/MAR.gpkg", gpkg_exists=True)[1]

    assert "-overwrite" not in retry
    assert "-skipfailures" in retry


def test_the_strict_pass_does_not_pay_the_skipfailures_penalty():
    """The whole point of the shared append module: -skipfailures pins -gt to 1,
    which cost 72 s per member against 1 s without it."""
    from src.groundswell_handler import merge_commands_for

    strict = merge_commands_for("/o.gpkg", "/MAR.gpkg", gpkg_exists=True)[0]

    assert "-skipfailures" not in strict


# ── routing ──────────────────────────────────────────────────────────────

def test_recognises_the_cmr_collection_url():
    """The importer takes one URL; this is the one that means Groundswell."""
    from src.groundswell_handler import is_groundswell_url

    assert is_groundswell_url(
        "https://cmr.earthdata.nasa.gov/search/granules.json"
        "?collection_concept_id=C3540918701-ESDIS"
    )
    assert is_groundswell_url(
        "https://cmr.earthdata.nasa.gov/virtual-directory/collections/"
        "C3540918701-ESDIS"
    )


def test_leaves_ordinary_urls_alone():
    from src.groundswell_handler import is_groundswell_url

    assert not is_groundswell_url(
        "https://data.geo.admin.ch/ch.swisstopo.geologie-geocover/x.gpkg.zip"
    )
