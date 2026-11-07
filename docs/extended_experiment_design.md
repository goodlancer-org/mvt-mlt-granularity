# Design Document: Extended Vector Tile Granularity Experiment

**Scope:** Research pipeline, experimental datasets, analysis, and manuscript  
**Objective:** Strengthen the empirical evaluation of spatial tile granularity by separating compression-unit benefits from changes in feature clipping and by comparing MLT v1 and MLT v2.

## 1. Goals

Extend the existing experimental pipeline to:

1. Replace the Python `maplibre_tiles` MVT-to-MLT converter with the official Rust-based MapLibre MLT implementation.
2. Produce both MLT v1 and MLT v2 using the same Rust encoder implementation and consistent configuration.
3. Add **Aggregated-4** and **Aggregated-16** tile variants that preserve the exact feature content of Standard tiles.
4. Separate compression improvements caused by larger independently encoded units from improvements associated with changes in feature clipping, buffering, and duplication.
5. Extend the statistical datasets, result tables, figures, and manuscript to support these comparisons.

The research focus remains the influence of spatial encoding-unit granularity on compression efficiency, not optimization or benchmarking of individual codecs.

## 2. Experimental Variants

The experiment shall include five tile variants for each of the five existing datasets.

| Variant | Area factor | Source content | Purpose |
|---|---:|---|---|
| Standard | 1× | Conventionally generated tiles | Baseline |
| Aggregated-4 | 4× | Exact feature content of 2×2 Standard tiles | Controlled aggregation |
| Aggregated-16 | 16× | Exact feature content of 4×4 Standard tiles | Controlled aggregation |
| Dense-4 | 4× | Independently generated at matched logical zoom | Realistic larger-tile generation |
| Dense-16 | 16× | Independently generated at matched logical zoom | Realistic larger-tile generation |

### 2.1. Aggregated variants

Aggregated-4 and Aggregated-16 shall preserve the complete multiset of features contained in their constituent Standard tiles, including:

- Geometry and coordinate precision, transformed into the aggregate tile coordinate system.
- Feature multiplicity resulting from clipping and buffering.
- Feature identifiers, attributes, values, and types.
- Geometry fragments crossing the original tile boundaries.

No feature merging, deduplication, additional simplification, or source-data regeneration is permitted in these variants.

Extents shall be 8192 and 16384, respectively.

### 2.2. Comparison conditions

All variants shall be compared over equivalent geographic regions at the same logical zoom. Aggregated-4 and Aggregated-16 must use the same underlying Standard tile content, regrouped into four or sixteen cells per encoding unit.

The existing Dense variants retain their current generation rules.

The design shall distinguish:

- **Compression-unit effect:** Standard versus Aggregated variants, using identical feature content.
- **Tile-regeneration effect:** Aggregated versus Dense variants at the same area factor, including changed feature clipping, buffering, and representation.
- **Total granularity effect:** Standard versus Dense variants, representing the existing experiment.

The tile-regeneration effect must not be attributed exclusively to feature clipping unless buffering and other content differences are separately controlled.

## 3. MLT Conversion

Replace Python-based MLT encoding with the official Rust MapLibre MLT encoder.

Requirements:

- Support conversion of all five tile variants into MLT v1 and MLT v2.
- Use the same pinned Rust implementation for both format versions.
- Apply equivalent encoder configuration wherever supported.
- Preserve MVT as the common input baseline for both MLT versions.
- Continue measuring raw and independently gzip-compressed tile sizes.
- Record encoder version, build identity, relevant options, and format version in experiment metadata.
- Validate encoded data and document any unavoidable semantic normalization or unsupported input representations.

No additional codec-option benchmarking is required.

The original Python-produced results shall be retained as historical reference data but replaced by Rust-produced results in the primary experimental comparisons.

## 4. Dataset and Statistical Model Changes

Extend the existing per-tile, per-layer, per-stream, and archive statistics to support five variants and three encoding formats.

### 4.1. Experiment dimensions

All results shall be identifiable by:

- Dataset and geographic study region.
- Logical zoom and spatial comparison block.
- Tile variant and granularity factor.
- Encoding format: MVT, MLT v1, or MLT v2.
- Compression state: raw or gzip.
- Encoder version and configuration.

### 4.2. Content and equivalence statistics

Add statistics for:

- Number of feature instances and unique source features.
- Number of stored vertices and geometry fragments.
- Repeated features and vertices resulting from clipping or buffering.
- Differences in feature and geometry counts between Aggregated and Dense variants.
- Attribute-type normalization and other semantic transformations.
- Validation results for equivalent-content comparisons.

These statistics must support comparisons both per tile and across the same geographic area.

### 4.3. Compression statistics

Retain the existing measurements and extend them to both MLT versions:

- Total encoded bytes, raw and gzip.
- MLT saving relative to MVT.
- Granularity gain relative to Standard.
- Bytes per stored vertex and per feature.
- MLT stream length, structural overhead, and payload bytes per value, where comparable across format versions.

Add an explicit decomposition of total size changes:

**Total size reduction = fixed-content aggregation reduction + tile-regeneration reduction.**

This decomposition shall use byte totals for identical geographic coverage, so its components are additive. Relative MLT-versus-MVT gains shall be reported separately.

All comparisons must distinguish address-weighted transferred bytes from unique stored archive payload bytes.

## 5. Results Tables and Figures

Update the existing manuscript tables and figures as follows.

| Existing component | Required changes |
|---|---|
| Table 4 — Granularity variants | Add Aggregated-4 and Aggregated-16 and distinguish content-preserving aggregation from regeneration |
| Table 5 — MLT versus MVT savings | Report MLT v1 and v2 results for all five variants, raw and gzip |
| Figure 6 — Savings by logical zoom | Extend to compare Aggregated and Dense effects; show MLT v1/v2 differences |
| Table 6 — Content-dependent savings | Separate fixed-content aggregation from regenerated-tile results |
| Table 7 — Stream structure | Add version-specific structural and payload statistics, using explicitly defined comparable measures |
| Table 8 — Bytes per vertex | Extend to five variants and both MLT versions |
| New table — Effect decomposition | Quantify aggregation-only, regeneration-related, and total size reductions for 4× and 16× granularities |
| New table — Content differences | Report feature multiplicity, clipping/fragmentation, buffering-related duplication, and vertex-count changes |

Preserve the existing dataset provenance and normalization documentation unless the underlying source data change.

Avoid presenting every experimental dimension in one oversized table. Detailed per-zoom and per-version results may be placed in supplementary material.

## 6. Manuscript Changes

### Section 1 — Introduction

Refine the contributions to distinguish controlled encoding-unit aggregation from realistic tile regeneration. Introduce MLT v1/v2 comparison as a robustness test of the relationship between columnar encoding and spatial granularity.

### Section 2 — Background and Related Work

Update the MLT discussion to cover relevant architectural differences between v1 and v2, particularly stream metadata and encoding efficiency.

### Section 3 — Data and Methods

Describe the five experimental variants, the Rust encoder, consistent conversion settings, fixed-content equivalence requirements, and expanded metrics.

Explicitly define the three comparisons: aggregation-only, regeneration-related, and total granularity effects.

### Section 4 — Results

Reorganize the results around:

1. Compression gains under fixed-content aggregation.
2. Additional effects from regenerated larger tiles.
3. Differences between MLT v1 and MLT v2.
4. Stream-level explanations of the observed effects.
5. Raw versus gzip compression and content-normalized results.

### Section 5 — Discussion

Evaluate whether the granularity effect persists across MLT versions, which improvements are independent of feature cutting, and how compression-unit size interacts with tile-generation policy.

### Section 6 — Threats to Validity

Update the discussion of content equivalence, differences between regenerated and aggregated tiles, experimental MLT v2 maturity, and remaining limitations in attributing individual compression mechanisms.

### Abstract and Conclusion

Replace the existing numerical conclusions with results from the expanded experiment.

Distinguish findings for controlled aggregation, realistic tile generation, and the two MLT versions.

## 7. Acceptance Criteria

The extension is complete when:

1. All five datasets have Standard, Aggregated-4, Aggregated-16, Dense-4, and Dense-16 variants for all applicable matched logical zooms.
2. Rust conversion produces MLT v1 and v2 outputs for every applicable variant using a documented and reproducible configuration.
3. Aggregated variants pass content-equivalence validation against their constituent Standard tiles.
4. Results separately quantify encoding-unit aggregation and tile-regeneration effects without conflating them.
5. Existing compression metrics remain reproducible and comparable after the encoder replacement.
6. All statistics, figures, and manuscript tables are regenerated from the extended dataset.
7. The manuscript's claims accurately reflect the controlled comparisons, distinguishing measured effects from proposed compression mechanisms.

## 8. Out of Scope

- Systematic optimization of individual MLT codec options.
- Development of new MLT encoding algorithms.
- Changes to the five source datasets or their geographic study regions.
- Client-side rendering and interactive network-performance benchmarks.
- Implementation of new map tiling standards or production rendering capabilities.

**Expected outcome:** An expanded, reproducible study that directly measures the compression benefits of larger encoding units, distinguishes them from feature-cutting and tile-regeneration effects, and evaluates whether the observed granularity dependence persists across MLT v1 and MLT v2.

## 9. Implementation and evidence

The implementation is described in [extended_experiment.md](extended_experiment.md).
Entry points are `src.experiment` (Docker) and `analysis.encode` (the same pinned
Rust core on the host). `analysis.extended` imports measurements;
`analysis/sql/extended.sql` defines matched-block comparisons;
`analysis.extended_report` generates the article inputs and acceptance checks.

Source identity is preserved in a separate lookup and explicit MVT feature IDs.
The exact-content control is at the MVT input boundary: larger units can change
MLT importer type normalization. Those transitions are measured and stated as a
limitation rather than treated as strict typed equivalence. Repeated ID/coordinate
counts and MoveTo components describe observable redundancy/fragmentation, without
claiming a causal partition into clipping and buffering.

Evidence is generated in `docs/data/extended_checks.md`, `extended_claims.json`
and the `extended_*.csv` exports; detailed observations are in
`docs/data/extended/`. Historical results remain separate. A local Zenodo mirror
is prepared without publishing or changing an existing DOI release.
