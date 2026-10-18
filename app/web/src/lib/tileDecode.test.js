import { describe, expect, test } from 'vitest';
import { summariseDecode, tileUrl } from './tileDecode';

// Decode time is the most direct test of MLT's central claim: that a columnar
// layout is cheaper to turn into features than MVT's per-feature protobuf.
describe('summariseDecode', () => {
  test('reports the median decode time across sampled tiles', () => {
    const out = summariseDecode([
      { ms: 4, bytes: 1024 },
      { ms: 2, bytes: 1024 },
      { ms: 9, bytes: 1024 },
    ]);

    expect(out.tile_decode_time_ms).toBe(4);
  });

  test('normalises by tile size so bigger tiles do not look slower', () => {
    // 8 ms for 4 KB is 2 ms/KB.
    const out = summariseDecode([{ ms: 8, bytes: 4096 }]);

    expect(out.tile_decode_time_per_kb_ms).toBe(2);
  });

  test('normalises using total time over total bytes, not a mean of ratios', () => {
    const out = summariseDecode([
      { ms: 1, bytes: 1024 },
      { ms: 9, bytes: 9216 },
    ]);

    // 10 ms over 10 KB.
    expect(out.tile_decode_time_per_kb_ms).toBe(1);
  });

  test('records how many tiles and bytes the figure came from', () => {
    const out = summariseDecode([{ ms: 1, bytes: 1024 }, { ms: 3, bytes: 1024 }]);

    expect(out.decoded_tile_count).toBe(2);
    expect(out.decoded_bytes).toBe(2048);
  });

  test('is null rather than zero when no tile could be decoded', () => {
    const out = summariseDecode([]);

    expect(out.tile_decode_time_ms).toBeNull();
    expect(out.tile_decode_time_per_kb_ms).toBeNull();
    expect(out.decoded_tile_count).toBe(0);
  });
});

describe('tileUrl', () => {
  test('addresses a tile in a dataset under one encoding', () => {
    expect(tileUrl('amsterdam', 'mlt', { z: 14, x: 8404, y: 5385 }))
      .toBe('/api/tiles/amsterdam/mlt/14/8404/5385');
  });

  test('escapes dataset names that need it', () => {
    expect(tileUrl('la geodatabase', 'mvt', { z: 1, x: 2, y: 3 }))
      .toBe('/api/tiles/la%20geodatabase/mvt/1/2/3');
  });
});
