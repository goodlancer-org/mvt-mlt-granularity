"""A dataset's name is what the paper calls it, not what its URL happens to end in.

The name derived from a URL becomes the protocol filename, every output
archive's prefix, every log name, and the row label in docs/results.md. Two of
the four study datasets derive a name that matches nothing the paper or the
documentation says:

    the canonical Saentis URL  -> "geologie-geocover_1115_2056"
    the Groundswell CMR URL    -> "granules"

The 2026-08-28 Saentis figures were recorded under "geocover_1115_saentis"
only because that import came from a hand-renamed local file. An automatic run
from the canonical URL would silently produce a second, differently-named
dataset, and results.md would stop matching the 22 places the docs refer to it.

So a study import states its name, and the derivation stays as the fallback for
ad-hoc imports through the UI.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.convert import dataset_name_from_url, resolve_dataset_name

SAENTIS_URL = (
    "https://data.geo.admin.ch/ch.swisstopo.geologie-geocover/"
    "geologie-geocover_1115/geologie-geocover_1115_2056.gpkg.zip"
)
GROUNDSWELL_URL = (
    "https://cmr.earthdata.nasa.gov/search/granules.json"
    "?collection_concept_id=C3540918701-ESDIS"
)


def test_an_explicit_name_wins_over_the_url():
    assert resolve_dataset_name(SAENTIS_URL, "geocover_1115_saentis") == (
        "geocover_1115_saentis")


def test_the_collection_url_would_otherwise_be_called_granules():
    """Documents the trap this function exists to avoid."""
    assert dataset_name_from_url(GROUNDSWELL_URL) == "granules"

    assert resolve_dataset_name(GROUNDSWELL_URL, "groundswell") == "groundswell"


def test_the_canonical_saentis_url_would_otherwise_not_match_the_docs():
    assert dataset_name_from_url(SAENTIS_URL) == "geologie-geocover_1115_2056"

    assert resolve_dataset_name(SAENTIS_URL, "geocover_1115_saentis") == (
        "geocover_1115_saentis")


def test_no_name_falls_back_to_the_derivation():
    """Ad-hoc imports through the UI pass no name and must keep working."""
    assert resolve_dataset_name(SAENTIS_URL, None) == dataset_name_from_url(
        SAENTIS_URL)
    assert resolve_dataset_name(SAENTIS_URL, "") == dataset_name_from_url(
        SAENTIS_URL)
    assert resolve_dataset_name(SAENTIS_URL, "   ") == dataset_name_from_url(
        SAENTIS_URL)


def test_a_supplied_name_is_still_made_filesystem_safe():
    """It becomes a filename and a URL path segment, so it cannot be trusted
    raw just because a caller supplied it."""
    assert resolve_dataset_name(SAENTIS_URL, "../../etc/passwd") == "etc-passwd"
    assert resolve_dataset_name(SAENTIS_URL, "My Dataset!") == "my-dataset"


def test_a_name_that_sanitises_to_nothing_falls_back_to_the_url():
    assert resolve_dataset_name(SAENTIS_URL, "///") == dataset_name_from_url(
        SAENTIS_URL)


def test_a_supplied_name_keeps_its_extension_like_suffixes_intact():
    """dataset_name_from_url strips .gpkg.zip and friends because they come
    from a filename. A name the caller chose is not a filename."""
    assert resolve_dataset_name(SAENTIS_URL, "krishna_giam_30m") == (
        "krishna_giam_30m")
