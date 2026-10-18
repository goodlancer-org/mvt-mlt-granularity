"""Tests for CityGML archive inspection.

CityGML archives are not always a single file. The Dutch BGT/IMGeo export,
for example, is one CityGML file per feature class (35 of them for a city
extract), so the converter has to convert every member, not just the biggest.
"""

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.citygml_handler import (
    extract_member,
    gml_sources_from_zip,
    layer_name_for_gml,
    list_gml_members,
    srs_from_gml_header,
)

# Namespace header as written by the PDOK BGT export: CityGML 2.0 carrying
# the IMGeo application domain extension.
BGT_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<CityModel xmlns:gml="http://www.opengis.net/gml"'
    ' xmlns:imgeo="http://www.geostandaarden.nl/imgeo/2.1"'
    ' xmlns="http://www.opengis.net/citygml/2.0">\n'
    '  <gml:boundedBy><gml:Envelope srsName="urn:ogc:def:crs:EPSG::28992"'
    ' srsDimension="2"/></gml:boundedBy>\n'
)


def _write_zip(tmp_path, members):
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, body in members.items():
            zf.writestr(name, body)
    return zip_path


def test_lists_every_gml_member_not_just_the_largest(tmp_path):
    zip_path = _write_zip(tmp_path, {
        "bgt_pand.gml": BGT_HEADER + "x" * 10,
        "bgt_wegdeel.gml": BGT_HEADER + "x" * 5000,
        "bgt_bak.gml": BGT_HEADER + "x" * 100,
        "readme.txt": "not gml",
    })

    assert list_gml_members(zip_path) == [
        "bgt_bak.gml",
        "bgt_pand.gml",
        "bgt_wegdeel.gml",
    ]


def test_layer_name_is_derived_from_the_gml_filename():
    assert layer_name_for_gml("bgt_pand.gml") == "bgt_pand"
    assert layer_name_for_gml("nested/dir/BGT_Wegdeel.GML") == "bgt_wegdeel"
    assert layer_name_for_gml("odd name-v2.gml") == "odd_name_v2"


def test_reads_epsg_code_from_gml_urn_srs_name():
    assert srs_from_gml_header(BGT_HEADER) == "EPSG:28992"


def test_returns_none_when_gml_declares_no_srs_name():
    """bgt_pand.gml ships without an srsName; callers fall back to a sibling's."""
    assert srs_from_gml_header(BGT_HEADER.replace(
        ' srsName="urn:ogc:def:crs:EPSG::28992"', ""
    )) is None


def test_members_without_srs_borrow_the_crs_declared_by_siblings(tmp_path):
    """7 of Amsterdam's 35 BGT layers omit srsName; without a fallback source
    CRS, ogr2ogr cannot reproject them and drops every feature."""
    zip_path = _write_zip(tmp_path, {
        "bgt_wegdeel.gml": BGT_HEADER,
        "bgt_pand.gml": BGT_HEADER.replace(
            ' srsName="urn:ogc:def:crs:EPSG::28992"', ""
        ),
    })

    fallback_by_layer = {
        layer: source_srs for _, layer, source_srs in gml_sources_from_zip(zip_path)
    }

    assert fallback_by_layer == {"bgt_pand": "EPSG:28992", "bgt_wegdeel": "EPSG:28992"}


def test_every_member_is_named_for_later_extraction(tmp_path):
    zip_path = _write_zip(tmp_path, {"bgt_bak.gml": BGT_HEADER})

    (member, _, _), = gml_sources_from_zip(zip_path)

    assert member == "bgt_bak.gml"


def test_extract_member_writes_the_member_to_disk(tmp_path):
    zip_path = _write_zip(tmp_path, {"bgt_bak.gml": BGT_HEADER})
    dest_dir = tmp_path / "scratch"
    dest_dir.mkdir()

    unpacked = extract_member(zip_path, "bgt_bak.gml", dest_dir)

    assert unpacked == dest_dir / "bgt_bak.gml"
    assert unpacked.read_text() == BGT_HEADER


def test_rejects_an_archive_containing_no_gml(tmp_path):
    zip_path = _write_zip(tmp_path, {"readme.txt": "nothing here"})

    try:
        gml_sources_from_zip(zip_path)
    except RuntimeError as exc:
        assert "No .gml files" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for a GML-free archive")
