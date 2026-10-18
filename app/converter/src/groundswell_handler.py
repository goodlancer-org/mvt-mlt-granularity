"""Acquire the Groundswell projections and merge them into one GeoPackage.

The dataset is distributed as one archive per country: 112 GeoPackages and 112
file geodatabases, 224 granules in all. Only the GeoPackages are taken --
taking both would count every country twice, and the paper reports feature
counts.

Discovery through CMR is anonymous. Download may not be: the direct URLs
redirect through a signed CloudFront link, and depending on the account's
approval state that redirect can land in an OAuth flow answering
`access_denied`. A bearer token minted from Earthdata credentials covers both
cases, so one is attached when credentials are available and the download is
attempted without one when they are not.

Everything after the collection URL is this module's job; the pipeline resumes
at an ordinary GeoPackage, exactly as it does for CityGML and CSV.
"""

import hashlib
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from .ogr_append import append_attempts

COLLECTION_ID = "C3540918701-ESDIS"
CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"

# Method.md states 112 countries. Any other number is a failure, not a warning:
# a partial merge still produces a plausible-looking GeoPackage.
EXPECTED_GRANULES = 112

URS = "https://urs.earthdata.nasa.gov"

# All 112 countries land here. The paper describes a single 1/8 degree grid
# spanning them; country identity survives in the NAME0/UCADMIN0 attributes, so
# merging loses nothing. Keeping 112 layers would make Groundswell 78% of every
# layer the study measures, swamping the density correlation with near-identical
# slabs of about 3,800 features each.
MERGED_LAYER = "groundswell"


# ------------------------------------------------------------- discovery

def granule_urls_from_cmr_json(payload):
    """Every -gpkg.zip download URL in a CMR granules response, sorted."""
    urls = []
    for entry in payload.get("feed", {}).get("entry", []):
        for link in entry.get("links", []):
            href = link.get("href", "")
            if href.endswith("-gpkg.zip"):
                urls.append(href)
                break
    return sorted(set(urls))


def verify_granule_count(urls):
    """Refuse anything but the full set.

    A partial merge still produces a GeoPackage that opens, converts and
    reports feature counts, so this fails rather than warns.
    """
    if len(urls) != EXPECTED_GRANULES:
        raise RuntimeError(
            "CMR returned %d GeoPackage granules, expected %d. "
            "Refusing to merge a partial dataset."
            % (len(urls), EXPECTED_GRANULES)
        )


def is_groundswell_url(url):
    """True for any CMR URL naming the Groundswell collection."""
    return "cmr.earthdata.nasa.gov" in url and COLLECTION_ID in url


# ------------------------------------------------------------ unwrapping

def country_gpkg_from_zip(zip_path, dest_dir):
    """Extract the one real GeoPackage file from a country archive.

    The archive nests it as <ISO3>.gpkg/<ISO3>.gpkg, so the match has to be on
    zip *entries*: a directory of that name is not something GDAL can open, and
    a naive glob finds the directory first. The bundled documentation PDF and
    the xlsx data dictionary are ignored.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        members = [
            name for name in archive.namelist()
            if name.lower().endswith(".gpkg") and not name.endswith("/")
        ]
        if not members:
            raise RuntimeError("no .gpkg file inside %s" % Path(zip_path).name)
        member = sorted(members)[0]
        target = dest_dir / Path(member).name
        with archive.open(member) as source, open(target, "wb") as out:
            shutil.copyfileobj(source, out)
    return target


# ---------------------------------------------------------------- schema

def schema_signature(fields):
    """A stable fingerprint of one layer's field names and types."""
    joined = ";".join("%s:%s" % (name, ftype) for name, ftype in fields)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


def verify_uniform_schemas(by_country):
    """All 112 countries must share one schema before they share one layer.

    Four were compared by hand; the rest were assumed. A country with an added,
    missing or retyped column merges as roughly 4,000 cells of null columns,
    which reads as data rather than as an error, so every country is checked.
    The majority signature is taken as correct and each country that disagrees
    is named, so the failure says which file to open.
    """
    signatures = {c: schema_signature(f) for c, f in by_country.items()}
    counts = {}
    for signature in signatures.values():
        counts[signature] = counts.get(signature, 0) + 1
    expected = max(counts, key=counts.get)
    odd = sorted(c for c, sig in signatures.items() if sig != expected)
    if odd:
        raise RuntimeError(
            "Groundswell country schemas disagree; cannot merge into one "
            "layer. Divergent: %s" % ", ".join(odd)
        )


def _schemas_for(country_gpkgs):
    """Field names and types per country, read with ogrinfo."""
    types = {"String", "Real", "Integer", "Integer64", "Date", "DateTime"}
    schemas = {}
    for path in country_gpkgs:
        iso = Path(path).stem.upper()
        out = subprocess.run(
            ["ogrinfo", "-so", str(path), "%s_projections" % iso],
            capture_output=True, text=True, timeout=120,
        ).stdout
        fields = []
        for line in out.splitlines():
            if ": " not in line:
                continue
            name, rest = line.split(": ", 1)
            ftype = rest.split(" ")[0].strip()
            if ftype in types:
                fields.append((name.strip(), ftype))
        schemas[iso] = fields
    return schemas


# ------------------------------------------------------------ credentials

def earthdata_credentials():
    """Earthdata login from the environment. Never read from a repo file."""
    user = os.environ.get("EDL_USERNAME")
    password = os.environ.get("EDL_PASSWORD")
    if not user or not password:
        raise RuntimeError(
            "Earthdata credentials required. Set EDL_USERNAME and "
            "EDL_PASSWORD, or put them in ~/.netrc for machine "
            "urs.earthdata.nasa.gov."
        )
    return user, password


def have_earthdata_credentials():
    """Whether a token can be minted without prompting anyone."""
    return bool(os.environ.get("EDL_USERNAME")
                and os.environ.get("EDL_PASSWORD"))


def earthdata_token(session=None):
    """Reuse a token already on the account, or mint one.

    Basic auth on the download URL is not enough on its own: it redirects into
    OAuth and can return access_denied unless the account has approved the
    egress application.
    """
    import requests

    session = session or requests.Session()
    user, password = earthdata_credentials()
    existing = session.get(
        "%s/api/users/tokens" % URS, auth=(user, password), timeout=60)
    if existing.status_code == 200 and existing.json():
        return existing.json()[0]["access_token"]
    minted = session.post(
        "%s/api/users/token" % URS, auth=(user, password), timeout=60)
    if minted.status_code not in (200, 201):
        raise RuntimeError(
            "could not obtain an Earthdata token: HTTP %d"
            % minted.status_code)
    return minted.json()["access_token"]


# ----------------------------------------------------------------- merge

def merge_commands_for(output_path, country_gpkg, gpkg_exists):
    """Strict then tolerant invocations for merging one country.

    retry_replaces_layer is False: all 112 countries share one layer, so an
    -overwrite retry would discard everything merged so far. A country that
    fails strictly has its own rows deleted before the tolerant pass.
    """
    return append_attempts(
        output_path, country_gpkg, MERGED_LAYER,
        gpkg_exists=gpkg_exists, retry_replaces_layer=False,
    )


def _delete_country_rows(output_path, country_gpkg):
    """Remove a half-written country before its tolerant retry.

    Without this the retry appends a second, overlapping copy of whatever the
    strict pass managed to write before it failed.
    """
    iso = Path(country_gpkg).stem.upper()
    subprocess.run(
        ["ogrinfo", str(output_path), "-sql",
         "DELETE FROM %s WHERE UCADMIN0 = '%s'" % (MERGED_LAYER, iso)],
        capture_output=True, text=True, timeout=600,
    )


def merge_to_single_layer(gpkg_paths, output_path, progress_callback=None):
    """Merge every country GeoPackage into one layer. Returns a summary."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged, failed, tolerated = [], [], []
    total = len(gpkg_paths)

    for index, country_gpkg in enumerate(sorted(gpkg_paths), start=1):
        iso = Path(country_gpkg).stem.upper()
        exists = output_path.exists()
        result = None
        attempt = 0
        for attempt, cmd in enumerate(
                merge_commands_for(output_path, country_gpkg, exists)):
            if attempt:
                if exists:
                    _delete_country_rows(output_path, country_gpkg)
                else:
                    output_path.unlink(missing_ok=True)
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode == 0:
                break
        if result is None or result.returncode != 0:
            failed.append(iso)
            detail = (result.stderr or "").strip()[-300:] if result else ""
            print("    [%d/%d] %s: FAILED - %s" % (index, total, iso, detail))
            continue
        merged.append(iso)
        if attempt:
            tolerated.append(iso)
        print("    [%d/%d] %s: ok%s"
              % (index, total, iso, " (features skipped)" if attempt else ""))
        if progress_callback and index % 10 == 0:
            progress_callback("convert", "Merged %d/%d countries" % (index, total))

    if failed:
        raise RuntimeError(
            "%d of %d countries failed to merge: %s"
            % (len(failed), total, ", ".join(failed))
        )
    return {"merged": merged, "tolerated": tolerated, "layer": MERGED_LAYER}


# ---------------------------------------------------------- orchestration

def groundswell_to_gpkg(url, dest_dir, progress_callback=None):
    """Discover, download, unwrap, verify and merge. Returns the GeoPackage."""
    import requests

    from .downloader import compute_sha256

    dest_dir = Path(dest_dir)
    downloads = dest_dir / "granules"
    unpacked = dest_dir / "countries"
    downloads.mkdir(parents=True, exist_ok=True)
    unpacked.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    payload = session.get(
        CMR_GRANULES,
        params={"collection_concept_id": COLLECTION_ID, "page_size": 300},
        timeout=120,
    ).json()
    urls = granule_urls_from_cmr_json(payload)
    verify_granule_count(urls)
    if progress_callback:
        progress_callback("download", "%d Groundswell granules to fetch" % len(urls))

    # Whether the CloudFront redirect actually demands a token depends on the
    # account's approval state, and the two sources of record disagree about it.
    # Attaching one when credentials exist covers both readings; without them
    # the download is attempted anonymously and fails loudly if that is refused.
    headers = {}
    if have_earthdata_credentials():
        headers["Authorization"] = "Bearer %s" % earthdata_token(session)
    elif progress_callback:
        progress_callback(
            "download",
            "No Earthdata credentials set; trying anonymous download")

    checksums, country_gpkgs = {}, []
    for index, granule in enumerate(urls, start=1):
        name = granule.rsplit("/", 1)[-1]
        archive = downloads / name
        if not archive.exists():
            response = session.get(granule, headers=headers, timeout=600)
            if response.status_code != 200:
                raise RuntimeError(
                    "%s: HTTP %d%s" % (
                        name, response.status_code,
                        "" if headers else
                        " (no Earthdata credentials were set; export "
                        "EDL_USERNAME and EDL_PASSWORD and retry)",
                    )
                )
            archive.write_bytes(response.content)
        # docs/maps.md requires a checksum per benchmark import: these archives
        # are mutable upstream and the paper reports figures taken from them.
        checksums[name] = compute_sha256(archive)
        country_gpkgs.append(country_gpkg_from_zip(archive, unpacked))
        if progress_callback and index % 10 == 0:
            progress_callback(
                "download", "Fetched %d/%d countries" % (index, len(urls)))

    verify_uniform_schemas(_schemas_for(country_gpkgs))

    output = dest_dir / "groundswell.gpkg"
    output.unlink(missing_ok=True)
    summary = merge_to_single_layer(country_gpkgs, output, progress_callback)
    print("  Merged %d countries into %s" % (len(summary["merged"]), output.name))
    if summary["tolerated"]:
        print("  Features skipped in: %s" % ", ".join(summary["tolerated"]))
    return output
