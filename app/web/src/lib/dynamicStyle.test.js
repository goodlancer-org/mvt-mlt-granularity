import { describe, expect, test, vi } from 'vitest';
import { buildDynamicStyle } from './dynamicStyle';

// A style with no dataset layers in it requests no tiles, and a benchmark run
// against one records zeros across every phase while missing_tile_count and
// console_error_count both report no problems. That is the shape of the
// Louisiana mlt_pmtiles run of 2026-08-28, and it is the same failure the
// Python side already fixed in generate_vector_profile: a source whose layer
// list came back empty converted quietly into a catch-all carrying none of the
// structure being measured.
describe('buildDynamicStyle with no layers to draw', () => {
  const PMTILES = 'pmtiles://http://localhost/data/output/la_mlt.pmtiles';

  test('falls back to a catch-all rather than throwing', () => {
    // `sourceUrl` was declared with const inside the else branch that builds the
    // PMTiles source, and read again from outside it, so the fallback raised
    // ReferenceError instead of producing a style.
    expect(() => buildDynamicStyle(PMTILES, [], { isMlt: true })).not.toThrow();
  });

  test('the catch-all still points at the archive it was asked for', () => {
    const style = buildDynamicStyle(PMTILES, [], { isMlt: true });

    expect(style.sources.dataset.url).toBe(PMTILES);
    expect(style.sources.dataset.encoding).toBe('mlt');
  });

  test('reports an error, so the correctness metrics cannot call it clean', () => {
    // console_error_count is defined as errors the browser reported during
    // visualization. A warning is not counted, so a catch-all style was
    // invisible to the one metric group meant to catch it.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    buildDynamicStyle(PMTILES, [], { isMlt: true });

    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  test('a source with layers is built normally and reports nothing', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const style = buildDynamicStyle(PMTILES, [{ id: 'wetlands', geometry_type: 'polygon' }]);

    expect(style.layers.some((l) => l.id !== 'background')).toBe(true);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
