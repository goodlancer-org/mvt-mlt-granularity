import { decodeTile as decodeMltTile } from '@maplibre/mlt';
import Pbf from 'pbf';
import { VectorTile } from '@mapbox/vector-tile';

/**
 * Tile decode benchmark.
 *
 * Decode cost belongs to the encoding, not the container: an MVT tile is the
 * same bytes whether it came out of MBTiles or PMTiles. So decode is measured
 * once per encoding, reading tiles through the tile API.
 *
 * Both decoders are timed over the same span — compressed bytes in, features
 * out — because MLT's decoder decompresses internally and excluding that for
 * one side only would flatter it.
 */

const DEFAULT_REPEATS = 5;

export function tileUrl(datasetName, encoding, { z, x, y }) {
  return `/api/tiles/${encodeURIComponent(datasetName)}/${encoding}/${z}/${x}/${y}`;
}

/** Combine per-tile decode samples into the reported figures. */
export function summariseDecode(samples) {
  if (samples.length === 0) {
    return {
      tile_decode_time_ms: null,
      tile_decode_time_per_kb_ms: null,
      decoded_tile_count: 0,
      decoded_bytes: 0,
    };
  }

  const times = samples.map((s) => s.ms).sort((a, b) => a - b);
  const mid = Math.floor(times.length / 2);
  const median = times.length % 2
    ? times[mid]
    : (times[mid - 1] + times[mid]) / 2;

  const totalMs = samples.reduce((n, s) => n + s.ms, 0);
  const totalBytes = samples.reduce((n, s) => n + s.bytes, 0);

  return {
    tile_decode_time_ms: round(median),
    tile_decode_time_per_kb_ms: totalBytes > 0
      ? round(totalMs / (totalBytes / 1024))
      : null,
    decoded_tile_count: samples.length,
    decoded_bytes: totalBytes,
  };
}

function round(n) {
  return Math.round(n * 1000) / 1000;
}

async function gunzipIfNeeded(bytes) {
  const isGzip = bytes.length > 2 && bytes[0] === 0x1f && bytes[1] === 0x8b;
  if (!isGzip || typeof DecompressionStream === 'undefined') return bytes;
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

async function decodeOnce(encoding, bytes) {
  if (encoding === 'mlt') {
    // decodeTile decompresses internally.
    return decodeMltTile(bytes);
  }
  const raw = await gunzipIfNeeded(bytes);
  return new VectorTile(new Pbf(raw));
}

/**
 * Fetch each tile once, then decode it repeatedly and time the decode.
 *
 * Fetching is outside the timed region; only decode is measured.
 */
export async function measureDecode({
  datasetName, encoding, tiles, repeats = DEFAULT_REPEATS,
}) {
  const samples = [];

  for (const tile of tiles) {
    let bytes;
    try {
      const response = await fetch(tileUrl(datasetName, encoding, tile));
      if (!response.ok || response.status === 204) continue;
      bytes = new Uint8Array(await response.arrayBuffer());
      if (bytes.length === 0) continue;
      // Warm up so the first timed pass is not paying for lazy initialisation.
      await decodeOnce(encoding, bytes);
    } catch (_) {
      continue;
    }

    const start = performance.now();
    for (let i = 0; i < repeats; i += 1) {
      await decodeOnce(encoding, bytes);
    }
    const elapsed = (performance.now() - start) / repeats;

    samples.push({ ms: elapsed, bytes: bytes.length });
  }

  return summariseDecode(samples);
}

/**
 * Tile coordinates covering the centre of a dataset's extent at a given zoom.
 */
export function sampleTilesForCenter(center, zoom, span = 2) {
  if (!center) return [];
  const [lon, lat] = center;
  const n = 2 ** zoom;
  const cx = Math.floor(((lon + 180) / 360) * n);
  const latRad = (lat * Math.PI) / 180;
  const cy = Math.floor(
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n,
  );

  const tiles = [];
  for (let dx = 0; dx < span; dx += 1) {
    for (let dy = 0; dy < span; dy += 1) {
      const x = cx + dx;
      const y = cy + dy;
      if (x >= 0 && y >= 0 && x < n && y < n) tiles.push({ z: zoom, x, y });
    }
  }
  return tiles;
}
