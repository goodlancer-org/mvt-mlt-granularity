import { beforeEach, describe, expect, test } from 'vitest';
import {
  countTileTraffic, recordTile, recordTileBytes, recordTileRequest,
  resetTileTraffic, sumTileTrafficBytes, tileByteLength, tileTrafficMark,
  tileTrafficSince, wireByteLength,
} from './tileTraffic';
import { benchTilesUrl, RecordingSource, tileFetchBytes } from './pmtiles';

const TILE = 'http://localhost:8080/api/tiles/amsterdam/mvt/10/525/336';
const ARCHIVE = 'http://localhost:8080/data/output/amsterdam_mlt.pmtiles';

beforeEach(() => resetTileTraffic());

describe('the tile ledger', () => {
  test('records bytes for every tile delivered', () => {
    recordTile(TILE, 1200);
    recordTile(ARCHIVE, 800);

    expect(sumTileTrafficBytes(tileTrafficSince(0))).toBe(2000);
    expect(countTileTraffic(tileTrafficSince(0))).toBe(2);
  });

  // Metrics are reported per phase (cold / pan / zoom), so each phase reads
  // only what arrived during it. A mark taken at the phase boundary is what
  // separates them.
  test('slices from a mark so phases do not double-count', () => {
    recordTile(TILE, 1200);
    const mark = tileTrafficMark();
    recordTile(TILE, 300);
    recordTile(TILE, 400);

    const phase = tileTrafficSince(mark);

    expect(countTileTraffic(phase)).toBe(2);
    expect(sumTileTrafficBytes(phase)).toBe(700);
  });

  test('a phase that fetched nothing sums to zero', () => {
    recordTile(TILE, 1200);
    const mark = tileTrafficMark();

    expect(sumTileTrafficBytes(tileTrafficSince(mark))).toBe(0);
    expect(countTileTraffic(tileTrafficSince(mark))).toBe(0);
  });

  // Every run is cold. A ledger carried over from the previous run would
  // attribute the previous format's traffic to this one.
  test('reset clears everything recorded so far', () => {
    recordTile(TILE, 1200);
    resetTileTraffic();

    expect(tileTrafficMark()).toBe(0);
    expect(countTileTraffic(tileTrafficSince(0))).toBe(0);
  });
});

// A tile counts as requested when the renderer asks for it: *_new_tile_requests
// is defined as the requests generated during a phase, and a request that fails
// or is aborted was still generated.
describe('requests and their bytes', () => {
  test('counts a request that never delivered, with no bytes', () => {
    recordTileRequest(TILE);

    expect(countTileTraffic(tileTrafficSince(0))).toBe(1);
    expect(sumTileTrafficBytes(tileTrafficSince(0))).toBe(0);
  });

  test('attributes bytes to the phase that made the request', () => {
    const record = recordTileRequest(TILE);
    const mark = tileTrafficMark();
    recordTileBytes(record, 1200);

    expect(sumTileTrafficBytes(tileTrafficSince(0))).toBe(1200);
    expect(countTileTraffic(tileTrafficSince(mark))).toBe(0);
  });
});

// PMTiles hands MapLibre a Uint8Array and the MBTiles handler an ArrayBuffer.
// Sizing only one of them counted a whole container as zero traffic.
describe('tileByteLength', () => {
  test('sizes both shapes of tile body', () => {
    expect(tileByteLength(new ArrayBuffer(1200))).toBe(1200);
    expect(tileByteLength(new Uint8Array(800))).toBe(800);
  });

  test('is zero for a body that is not a tile', () => {
    expect(tileByteLength(null)).toBe(0);
    expect(tileByteLength({ tilejson: '3.0.0' })).toBe(0);
  });
});

// MBTiles tiles must go through a protocol handler, not a plain `tiles:` URL,
// or MapLibre fetches them in a worker where the ledger cannot see them.
describe('benchTilesUrl', () => {
  test('prefixes an http tile template with the recording protocol', () => {
    expect(benchTilesUrl('http://localhost:8080/api/tiles/amsterdam/mvt/{z}/{x}/{y}'))
      .toBe('benchtiles://http://localhost:8080/api/tiles/amsterdam/mvt/{z}/{x}/{y}');
  });

  test('leaves an already-prefixed url alone', () => {
    expect(benchTilesUrl('benchtiles://http://localhost:8080/api/tiles/a/mvt/{z}/{x}/{y}'))
      .toBe('benchtiles://http://localhost:8080/api/tiles/a/mvt/{z}/{x}/{y}');
  });
});

// The paper defines the byte metrics as tile data *transferred*. Tiles are
// stored gzipped in both containers, and both delivery paths inflate them
// before MapLibre sees them -- so the body handed to the renderer is several
// times what crossed the network.
describe('wireByteLength', () => {
  test('counts the bytes that crossed the network, not the inflated body', () => {
    expect(wireByteLength('1201', new ArrayBuffer(9800))).toBe(1201);
  });

  test('falls back to the body when the server reported no length', () => {
    expect(wireByteLength(null, new Uint8Array(800))).toBe(800);
    expect(wireByteLength('not-a-number', new Uint8Array(800))).toBe(800);
  });
});

// PMTiles inflates inside the library, so the compressed length is only
// observable at the byte range the archive was read from.
describe('the recording PMTiles source', () => {
  const fakeSource = () => ({
    getKey: () => ARCHIVE,
    getBytes: async (_offset, length) => ({ data: new ArrayBuffer(length) }),
  });

  test('notes the size of every range fetch and passes the bytes through', async () => {
    const source = new RecordingSource(fakeSource());

    const result = await source.getBytes(0, 16384);

    expect(result.data.byteLength).toBe(16384);
    expect(source.fetches).toEqual([16384]);
  });

  test('keeps the archive key, so the protocol resolves tiles through it', () => {
    expect(new RecordingSource(fakeSource()).getKey()).toBe(ARCHIVE);
  });
});

describe('tileFetchBytes', () => {
  // A tile request reads the header and a directory before the tile itself,
  // and only the last of those is the tile body.
  test('is the last range fetch of the request, not its directory reads', () => {
    expect(tileFetchBytes([16384, 4096, 1201], 0, 9800)).toBe(1201);
  });

  test('ignores fetches made before the request started', () => {
    expect(tileFetchBytes([16384, 1201], 1, 9800)).toBe(1201);
  });

  test('falls back to the delivered body when nothing was fetched', () => {
    expect(tileFetchBytes([16384], 1, 9800)).toBe(9800);
  });
});
