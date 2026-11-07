"""Build the framed research CLI against the exact maplibre-tiles 0.4.1 sdist.

Encoding code is unchanged. Budget-only patches expose explicit limits in the
MVT importer and annotated walker; existing APIs retain their original defaults.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
from build_mlt import SDIST_URL, SDIST_SHA256

FAST_MVT_SHA256='4dd28eb5048f310a33f947a615fbbca7ea47fc92e3a0820fc2a5925b475a8531'


def patch_mvt_budget(source,work,offline):
    """Expose Buffa's element-memory budget without touching codec algorithms."""
    vendor=source/'vendor/fast-mvt-0.7.1'
    if not vendor.exists():
        cache=Path(os.environ.get('CARGO_HOME',str(Path.home()/'.cargo')))/'registry/cache'
        archives=list(cache.glob('*/fast-mvt-0.7.1.crate'))
        archive=archives[0] if archives else work/'fast-mvt-0.7.1.crate'
        if not archive.exists():
            if offline:raise FileNotFoundError('Cached fast-mvt-0.7.1.crate required for offline build')
            urllib.request.urlretrieve('https://static.crates.io/crates/fast-mvt/fast-mvt-0.7.1.crate',archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=FAST_MVT_SHA256:
            raise RuntimeError('fast-mvt source checksum mismatch')
        with tarfile.open(archive) as tar:tar.extractall(source/'vendor',filter='data')
    reader=vendor/'src/reader/tile.rs';text=reader.read_text(encoding='utf-8')
    if 'pub fn new_with_max_element_memory' not in text:
        start=text.index('    pub fn new(data:')
        end=text.index('\n    pub fn layers(',start)
        original=text[start:end]
        explicit=original.replace("pub fn new(data: &'a [u8])", "pub fn new_with_max_element_memory(data: &'a [u8], max_size: usize)")
        explicit=explicit.replace('TileView::decode_view(data)?',
            'buffa::DecodeOptions::default().with_element_memory_limit(max_size).decode_view::<TileView>(data)?')
        text=text[:end]+'\n'+explicit+text[end:]
    text=text.replace('TileView::decode_view_with_options(data, &buffa::DecodeOptions::default().with_element_memory_limit(max_size))?',
        'buffa::DecodeOptions::default().with_element_memory_limit(max_size).decode_view::<TileView>(data)?')
    reader.write_text(text,encoding='utf-8')
    workspace=source/'Cargo.toml';text=workspace.read_text(encoding='utf-8')
    if '[patch.crates-io]' not in text:
        text+='\n[patch.crates-io]\nfast-mvt = { path = "vendor/fast-mvt-0.7.1" }\n'
        workspace.write_text(text,encoding='utf-8')
    decoder=source/'mlt-core/src/convert/mvt/decode.rs';text=decoder.read_text(encoding='utf-8')
    if 'pub fn mvt_to_tile_layers_with_max_size' not in text:
        start=text.index('pub fn mvt_to_tile_layers(data:')
        end=text.index('\n/// Build a',start)
        explicit=text[start:end].replace('pub fn mvt_to_tile_layers(data: impl AsRef<[u8]>)',
            'pub fn mvt_to_tile_layers_with_max_size(data: impl AsRef<[u8]>, max_size: usize)')
        explicit=explicit.replace('MvtReaderRef::new(data.as_ref())?',
            'MvtReaderRef::new_with_max_element_memory(data.as_ref(), max_size)?')
        text=text[:end]+'\n'+explicit+text[end:];decoder.write_text(text,encoding='utf-8')
        exports=source/'mlt-core/src/convert/mvt/mod.rs'
        exports.write_text(exports.read_text(encoding='utf-8').replace(
            '{mvt_to_feature_collection, mvt_to_tile_layers}',
            '{mvt_to_feature_collection, mvt_to_tile_layers, mvt_to_tile_layers_with_max_size}'),encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, default=Path('temp/mlt-native-build'))
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('app/converter/bin'))
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    adapter = Path(__file__).parent/'rust'
    output=args.output_dir.resolve()
    executable = 'mlt-experiment.exe' if __import__('os').name == 'nt' else 'mlt-experiment'
    existing=output/'mlt-build.json'
    if existing.exists() and (output/executable).exists():
        old=json.loads(existing.read_text())
        current={p.relative_to(adapter).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(adapter.rglob('*')) if p.is_file() and (p.suffix=='.rs' or p.name in ('Cargo.toml','Cargo.lock'))}
        if old.get('builder_sha256')==hashlib.sha256(Path(__file__).read_bytes()).hexdigest() and old.get('source_sha256')==SDIST_SHA256 and old.get('adapter_sha256')==current and old.get('binary_sha256')==hashlib.sha256((output/executable).read_bytes()).hexdigest():
            print(output/executable);return
    work = args.work_dir.resolve(); work.mkdir(parents=True, exist_ok=True)
    source = args.source_dir.resolve() if args.source_dir else work/'maplibre_tiles-0.4.1'
    if not source.exists():
        archive = work/'source.tar.gz'
        if not archive.exists(): urllib.request.urlretrieve(SDIST_URL, archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != SDIST_SHA256:
            raise RuntimeError('MLT source checksum mismatch')
        with tarfile.open(archive) as tar: tar.extractall(work, filter='data')
    workspace = source/'Cargo.toml'
    text = workspace.read_text(encoding='utf-8')
    if '"mlt-experiment"' not in text:
        text = text.replace('members = ["mlt-core", "mlt-py"]', 'members = ["mlt-core", "mlt-py", "mlt-experiment"]')
        workspace.write_text(text, encoding='utf-8')
    walker = source/'mlt-core/src/dump/walker.rs'
    text = walker.read_text(encoding='utf-8')
    if 'fn annotate_tile_with_max_size' not in text:
        text = text.replace('    let mut w = Walker {',
            '    annotate_tile_with_max_size(buf, 64 * 1024 * 1024)\n}\n\n'
            'pub fn annotate_tile_with_max_size(buf: &[u8], max_size: u32) -> (DumpTree, Option<MltError>) {\n'
            '    let mut w = Walker {', 1).replace('parser: Parser::default(),', 'parser: Parser::with_max_size(max_size),', 1)
        walker.write_text(text, encoding='utf-8')
        exports = source/'mlt-core/src/dump/mod.rs'
        exports.write_text(exports.read_text(encoding='utf-8').replace('pub use crate::dump::walker::annotate_tile;',
            'pub use crate::dump::walker::{annotate_tile, annotate_tile_with_max_size};'), encoding='utf-8')
    patch_mvt_budget(source,work,args.offline)
    shutil.copytree(adapter, source/'mlt-experiment', dirs_exist_ok=True)
    if (adapter/'Cargo.lock').exists(): shutil.copy2(adapter/'Cargo.lock', source/'Cargo.lock')
    subprocess.run(['cargo', 'build', '--release', '-p', 'mlt-experiment', '--locked',
                    *(['--offline'] if args.offline else [])], cwd=source, check=True)
    # Freeze all transitive dependencies in the released adapter source.
    shutil.copy2(source/'Cargo.lock', adapter/'Cargo.lock')
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=True)
    executable = 'mlt-experiment.exe' if __import__('os').name == 'nt' else 'mlt-experiment'
    shutil.copy2(source/'target/release'/executable, output/executable)
    provenance = {'binding_version':'0.4.1','core_version':'0.22.1','source_sha256':SDIST_SHA256,
        'builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'mvt_budget_patch':{'dependency':'fast-mvt 0.7.1','source_sha256':FAST_MVT_SHA256,
            'upstream_default_element_memory_mib':32,'scope':'Expose explicit Buffa element-memory budget; no encoding changes'},
        'upstream_commit':'e7bc737dc96f734a8549a41844b8aaf43ee50723',
        'rustc':subprocess.check_output(['rustc','--version'],text=True).strip(),
        'binary_sha256':hashlib.sha256((output/executable).read_bytes()).hexdigest(),
        'adapter_sha256':{p.relative_to(adapter).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(adapter.rglob('*')) if p.is_file() and (p.suffix=='.rs' or p.name in ('Cargo.toml','Cargo.lock'))},
        'options':{'profile':'native/4g','tessellation':'off','sort':'none','fsst':True,
            'fastpfor':True,'shared_dict':True,'v2_float_alp':False,'v2_float_dict':False,
            'v2_packed_dict_codes':True,'delta2':False,'rans_vertices':False}}
    (output/'mlt-build.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(output/executable)

if __name__ == '__main__': main()
