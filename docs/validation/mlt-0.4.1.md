# maplibre-tiles 0.4.1 validation

> Historical retained-corpus audit. The later regenerated five-variant experiment,
> including the Docker builds and Rust v1/v2 validation, is documented in
> [extended_experiment.md](../extended_experiment.md). Its primary results are
> separate; statements below about retained measurements and the unavailable
> Docker daemon describe the earlier audit stage.

The 2026-11-06 upgrade retains every original PMTiles archive and all compression
measurements. New conversions and repeat validation pin `maplibre-tiles==0.4.1`.
Historical encoder provenance is retained rather than relabelled as 0.4.1.

## Native memory budget

| Decoder | Budget | Failures among the original 48 addresses |
|---|---:|---:|
| Historical 0.1.31 audit | 20 MiB | 48 |
| Unmodified 0.4.1 | 64 MiB | 17 |
| 0.4.1 with explicit Rust budget | 256 MiB | 0 |

The remaining 64 MiB failures are five Natural Earth and twelve PDOK addresses.
The original failures were 22 Natural Earth, 25 PDOK and one USFWS address.
[Machine-readable per-tile evidence](mlt-0.4.1-memory.json) includes coordinates,
raw payload sizes, errors and the tested Windows wheel SHA-256.

`app/converter/build_mlt.py` verifies the official 0.4.1 source archive SHA-256
`dd35bb6771b59006efd505afb102334e37e1af53b17e640d3a6438e917663aa3` and adds
`max_memory_bytes` to the Python binding's two decode functions. The argument is
passed to both `Parser::with_max_size` and `Decoder::with_max_size`. No encoder
or mlt-core code is changed. The source is available from
[PyPI 0.4.1](https://pypi.org/project/maplibre-tiles/0.4.1/).

The active converter and analysis use `MLT_DECODE_MEMORY_MIB`, default 256. This
allocation accounting is not a limit on total Python, WKB, process or Docker RAM.
During the Windows full audit, one worker had already reached a peak working
set of 3,177,406,464 bytes (about 2.96 GiB). This is an implementation diagnostic,
not a rendering-memory benchmark or a portable container-memory bound.
The codec version and budget invalidate analysis caches. Metadata also records
`mlt_binding_patch=memory-budget-v1` and `mlt_decode_memory_bytes=268435456`.

## Installation

Use `python manage.py env` or rebuild the converter Docker image. Both install
the patched binding. For manually managed environments:

```sh
python app/converter/build_mlt.py --install
```

Host source builds require Rust >=1.98 and native build tools (Visual C++ on
Windows). The Docker build uses a separate Rust build stage and installs only
the resulting wheel in the runtime image. The runtime dependency lock still
identifies the upstream 0.4.1 package; the documented binding patch is built from
its checksum-verified source. A bare `uv sync --frozen` installs the upstream
binding; use `manage.py env` to apply the project patch as well. After setup,
use `uv run --no-sync ...` when invoking tools through uv, so it retains the
project binding instead of synchronizing back to the upstream wheel.

## Tests

Both repository copies passed 24 analysis tests and 16 focused converter tests.
The main real-world classification/comparison tests passed (31 passed, one skipped).
The cache and memory tests were repeated after extending coverage for codec
version invalidation. They exercise a real Rust rejection at a one-byte budget
and successful decoding with a larger budget, including the GeoJSON entry point.

The broader main converter suite has 210 passing tests and an unrelated failure
in `test_reconverting_keeps_render_metrics` (`render_metrics` is absent); this failure was also reproduced with the original
`protocol.py` from Git HEAD without changing working files. Two
legacy tests fail collection because `src.results` no longer exports
`CONVERSION_METRICS` or `render_rows`. These results are not reported as a clean
full-suite pass. Docker Compose configuration validates; the image build itself
has not been tested because Docker Desktop's Linux daemon is not running.

## Full retained-corpus audit

The full audit reruns every archive pair. All 30 main/Zenodo PMTiles files were verified byte-identical.
Before reusing historical source and
normalized bounds, all source, GPKG, configuration and archive input hashes were
verified unchanged against the previous audit manifest. Tile geometry envelopes
and pair diagnostics are recomputed with 0.4.1 and the configured budget. Source
bounds are reused without reinterpreting their original measurement provenance.

Strict typed/geometry equality remains a diagnostic separate from complete
address coverage and successful decoding. Raising the memory budget does not
repair existing type coercion, geometry differences or source-bounds checks.

### Completed corpus result

All **15 pairs / 36,647 addresses** were decoded and compared: **zero decoder
errors, zero missing MVT addresses and zero missing MLT addresses**. Strict
comparison retains **26,870 differing addresses** and no strictly equal archive
pairs; these differences are not silently accepted as semantic equality.
[Per-pair corpus results and environment](mlt-0.4.1-corpus.json) preserve archive
hashes and counts. The remaining report failure is the existing declared-bounds
check; the decoder/address-coverage gate now passes.

The statistics refresh verifies that `variant_summary`, `granularity_gain` and
`archive_totals` are exactly unchanged. Existing figures are retained because their
archive inputs and compression measurements are unchanged. Only audit diagnostics,
geometry envelopes and their exports are refreshed.
