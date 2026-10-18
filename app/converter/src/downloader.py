"""Download source files with resume support."""

import hashlib
import sys
from pathlib import Path

import requests


def _filename_from_response_or_url(url):
    """Resolve filename from Content-Disposition header (HEAD request), falling back to URL path."""
    import re
    try:
        head = requests.head(url, timeout=10, allow_redirects=True)
        cd = head.headers.get("Content-Disposition", "")
        match = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';\r\n]+)', cd, re.IGNORECASE)
        if match:
            return match.group(1).strip().strip('"\'')
    except Exception:
        pass
    filename = url.split("?")[0].split("/")[-1]
    return filename or "download"


def download_file(url, dest_dir, filename=None):
    """
    Download a file from URL to dest_dir with resume support.

    Returns the path to the downloaded file.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        filename = _filename_from_response_or_url(url)

    dest_path = dest_dir / filename

    # Check if file already exists and get its size for resume
    existing_size = dest_path.stat().st_size if dest_path.exists() else 0

    headers = {}
    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"
        print(f"Resuming download from {existing_size} bytes...")

    response = requests.get(url, headers=headers, stream=True, timeout=60)

    # If server returns 416 (Range Not Satisfiable), file is complete
    if response.status_code == 416:
        print(f"File already complete: {dest_path}")
        return dest_path

    response.raise_for_status()

    # Determine total size
    if response.status_code == 206:  # Partial Content
        content_range = response.headers.get("Content-Range", "")
        total_size = int(content_range.split("/")[-1]) if "/" in content_range else None
        mode = "ab"
    else:
        total_size = int(response.headers.get("Content-Length", 0)) or None
        existing_size = 0
        mode = "wb"

    downloaded = existing_size
    chunk_size = 8192

    with open(dest_path, mode) as f:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size:
                    pct = downloaded / total_size * 100
                    mb = downloaded / (1024 * 1024)
                    total_mb = total_size / (1024 * 1024)
                    sys.stdout.write(f"\r  {mb:.1f}/{total_mb:.1f} MB ({pct:.1f}%)")
                    sys.stdout.flush()

    print(f"\n  Downloaded: {dest_path} ({downloaded} bytes)")
    return dest_path


def compute_sha256(path, chunk_size=1024 * 1024):
    """SHA-256 of a file, read in chunks so large archives do not load whole.

    docs/maps.md requires a checksum per benchmark import because the upstream
    archives are mutable and a reported figure is only attributable to the
    bytes it came from. compute_md5 below predates that requirement and is kept
    for the callers that already use it.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_md5(filepath):
    """Compute MD5 hash of a file."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
