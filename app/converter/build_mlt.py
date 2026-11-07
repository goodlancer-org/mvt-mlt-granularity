"""Build maplibre-tiles 0.4.1 with an explicit native decode-memory argument.

Only the Python binding changes; mlt-core and encoder settings are unmodified.
Requires Rust >=1.98 and a native C/C++ toolchain (MSVC on Windows).
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import subprocess
import shutil
import sys
import tarfile
import urllib.request

VERSION = "0.4.1"
SDIST_URL = "https://files.pythonhosted.org/packages/eb/b1/5d96d36e5c68e8886b549f7dbbde960ba7c77470faae78e734f7760de720/maplibre_tiles-0.4.1.tar.gz"
SDIST_SHA256 = "dd35bb6771b59006efd505afb102334e37e1af53b17e640d3a6438e917663aa3"


def patch_binding(source: Path) -> None:
    path = source / "mlt-py/src/lib.rs"
    text = path.read_text(encoding="utf-8")
    if "max_memory_bytes: u32" in text:
        return
    start = text.index('#[pyo3(signature = (data, z=None, x=None, y=None, tms=true))]')
    end = text.index('/// Return a list of layer names', start)
    original = text[start:end]
    updated = original.replace(
        '(data, z=None, x=None, y=None, tms=true)',
        '(data, z=None, x=None, y=None, tms=true, *, max_memory_bytes=67108864)',
    ).replace('    tms: bool,\n', '    tms: bool,\n    max_memory_bytes: u32,\n')
    updated = updated.replace(
        '#[pyfunction]\nfn decode_mlt_to_geojson(',
        '#[pyfunction]\n#[pyo3(signature = (data, *, max_memory_bytes=67108864))]\nfn decode_mlt_to_geojson(',
    ).replace(') -> PyResult<String> {', '    max_memory_bytes: u32,\n) -> PyResult<String> {')
    if updated.count('max_memory_bytes: u32') != 2:
        raise RuntimeError('Unexpected upstream binding layout; refusing to patch')
    updated = updated.replace('Decoder::default()', 'Decoder::with_max_size(max_memory_bytes)')
    updated = updated.replace('Parser::default()', 'Parser::with_max_size(max_memory_bytes)')
    path.write_text(text[:start] + updated + text[end:], encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, default=Path('temp/mlt-native-build'))
    parser.add_argument('--wheel-dir', type=Path, default=Path('temp/mlt-wheels'))
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    if args.install:
        # Probe in a child: loading the Windows DLL here would lock it while pip
        # attempts to replace the unpatched installation.
        probe = subprocess.run([sys.executable, '-c',
            'import maplibre_tiles; from importlib.metadata import version; '
            'assert version("maplibre-tiles") == "0.4.1"; '
            'assert "max_memory_bytes" in maplibre_tiles.decode_mlt.__text_signature__'],
            capture_output=True)
        if probe.returncode == 0:
            print("Budget-enabled maplibre-tiles 0.4.1 is already installed")
            return
    work = args.work_dir.resolve(); work.mkdir(parents=True, exist_ok=True)
    wheels = args.wheel_dir.resolve(); wheels.mkdir(parents=True, exist_ok=True)
    source = args.source_dir.resolve() if args.source_dir else work / f'maplibre_tiles-{VERSION}'
    if not source.exists():
        archive = work / f'maplibre_tiles-{VERSION}.tar.gz'
        if not archive.exists():
            urllib.request.urlretrieve(SDIST_URL, archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != SDIST_SHA256:
            raise RuntimeError('Upstream source checksum mismatch')
        with tarfile.open(archive) as tar:
            tar.extractall(work, filter='data')
    patch_binding(source)
    uv = shutil.which('uv')
    if uv:
        # uv-created environments need not contain pip.
        build = [uv, 'build', '--native-tls', '--python', sys.executable,
                 '--cache-dir', str(work/'uv-cache'), '--wheel', '--out-dir', str(wheels), str(source)]
    else:
        build = [sys.executable, '-m', 'pip', 'wheel', '--no-deps',
                 '--wheel-dir', str(wheels), str(source)]
    subprocess.run(build, check=True)
    wheel = max(wheels.glob('maplibre_tiles-0.4.1-*.whl'), key=lambda p: p.stat().st_mtime_ns)
    if args.install:
        install = ([uv, 'pip', 'install', '--python', sys.executable, '--reinstall-package',
                    'maplibre-tiles', '--no-deps', str(wheel)] if uv else
                   [sys.executable, '-m', 'pip', 'install', '--force-reinstall', '--no-deps', str(wheel)])
        subprocess.run(install, check=True)
        subprocess.run([sys.executable, '-c',
                        'import maplibre_tiles; '
                        'assert "max_memory_bytes" in maplibre_tiles.decode_mlt.__text_signature__'], check=True)
    print(wheel)


if __name__ == '__main__':
    main()
