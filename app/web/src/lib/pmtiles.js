import * as pmtiles from 'pmtiles';
import maplibregl from 'maplibre-gl';
import {
  recordTileBytes, recordTileRequest, tileByteLength, wireByteLength,
} from './tileTraffic';

let protocolRegistered = false;
let rtlPluginLoaded = false;
const archiveCache = new Map();

/**
 * Initialize MapLibre with PMTiles protocol and RTL text plugin.
 * Must be called once before creating any Map instance.
 * PMTiles + MapLibre handles MLT tiles natively (since MapLibre GL JS v5.12+).
 */
export function initMaplibre() {
  registerPMTilesProtocol();
  loadRTLPlugin();
}

const BENCH_TILES_SCHEME = /^benchtiles:\/\//;
const PMTILES_TILE_URL = /^pmtiles:\/\/(.+)\/\d+\/\d+\/\d+$/;

/**
 * A PMTiles byte source that notes the size of every range it reads.
 *
 * The library inflates a tile before returning it, so the transferred length is
 * only observable at the range request the archive was read from. Wrapping the
 * source is also what keeps header and directory reads out of the tile figures:
 * they are separate ranges, and only the last one of a tile request is the tile.
 */
export class RecordingSource {
  constructor(inner) {
    this.inner = inner;
    this.fetches = [];
  }

  getKey() {
    return this.inner.getKey();
  }

  setHeaders(headers) {
    if (this.inner.setHeaders) this.inner.setHeaders(headers);
  }

  async getBytes(offset, length, signal, etag) {
    const result = await this.inner.getBytes(offset, length, signal, etag);
    this.fetches.push(result.data.byteLength);
    return result;
  }
}

/** The transferred size of the tile a request ended on, or the delivered body. */
export function tileFetchBytes(fetches, mark, fallback) {
  const during = fetches.slice(mark);
  return during.length ? during[during.length - 1] : fallback;
}

/** Archives served through a recording source, keyed by archive URL. */
const recordingArchives = new Map();

function recordingArchive(protocol, tileUrl) {
  const match = tileUrl.match(PMTILES_TILE_URL);
  const archiveUrl = (match ? match[1] : tileUrl).replace(/^pmtiles:\/\//, '');

  let source = recordingArchives.get(archiveUrl);
  if (!source) {
    source = new RecordingSource(new pmtiles.FetchSource(archiveUrl));
    // Registered on the protocol so its own lookup resolves to this instance
    // rather than constructing an unrecorded one.
    protocol.add(new pmtiles.PMTiles(source));
    recordingArchives.set(archiveUrl, source);
  }
  return source;
}

/**
 * Register the tile protocols with MapLibre GL JS.
 *
 * Both containers are served through `addProtocol` handlers so their traffic is
 * counted the same way. PMTiles needs a handler anyway; MBTiles is given one
 * (`benchtiles://`) purely so its bytes are visible on the main thread — a
 * plain `tiles:` URL is fetched inside a MapLibre worker, where the ledger and
 * the window's Resource Timing buffer both miss it.
 */
export function registerPMTilesProtocol() {
  if (protocolRegistered) return;

  const protocol = new pmtiles.Protocol({ metadata: true });
  maplibregl.addProtocol('pmtiles', async (params, abortController) => {
    // The same handler serves the TileJSON document; only tile bodies count,
    // and MapLibre marks that request as `json`.
    if (params.type === 'json') return protocol.tile(params, abortController);

    const source = recordingArchive(protocol, params.url);
    const mark = source.fetches.length;
    const record = recordTileRequest(params.url);
    const result = await protocol.tile(params, abortController);
    recordTileBytes(
      record,
      tileFetchBytes(source.fetches, mark, tileByteLength(result?.data)),
    );
    return result;
  });

  maplibregl.addProtocol('benchtiles', async (params, abortController) => {
    const url = params.url.replace(BENCH_TILES_SCHEME, '');
    const record = recordTileRequest(url);
    const response = await fetch(url, { signal: abortController.signal });
    if (!response.ok) throw new Error(`Tile request failed: ${response.status} ${url}`);
    const data = await response.arrayBuffer();
    // `fetch` has already inflated the body; Content-Length is what was sent.
    recordTileBytes(record, wireByteLength(response.headers.get('content-length'), data));
    return { data };
  });

  protocolRegistered = true;
}

/** Route an HTTP tile-URL template through the recording protocol. */
export function benchTilesUrl(httpUrl) {
  return BENCH_TILES_SCHEME.test(httpUrl) ? httpUrl : `benchtiles://${httpUrl}`;
}

/**
 * Load the RTL text plugin for Hebrew/Arabic text rendering.
 * Uses lazy mode — plugin is downloaded only when RTL text is encountered.
 */
export function loadRTLPlugin() {
  if (rtlPluginLoaded) return;

  try {
    maplibregl.setRTLTextPlugin(
      '/maplibre-plugins/rtl-text.js',
      true // lazy mode
    );
    rtlPluginLoaded = true;
  } catch (e) {
    // Plugin may already be loaded or not available
    console.warn('RTL plugin load warning:', e.message);
  }
}

/**
 * Build a MapLibre source URL for a PMTiles file.
 * @param {string} filename - e.g. "monaco_mlt.pmtiles"
 * @returns {string} pmtiles:// URL
 */
export function pmtilesUrl(filename) {
  // Use absolute path relative to the web server
  const base = window.location.origin;
  return `pmtiles://${base}/data/output/${filename}`;
}

function pmtilesHttpUrl(filename) {
  const base = window.location.origin;
  return `${base}/data/output/${filename}`;
}

function getArchive(filename) {
  if (!archiveCache.has(filename)) {
    archiveCache.set(filename, new pmtiles.PMTiles(pmtilesHttpUrl(filename)));
  }
  return archiveCache.get(filename);
}

/**
 * Drop cached PMTiles archives.
 *
 * Each archive holds its parsed header and directory in memory, so a second
 * measurement of the same file would start warm. The benchmark reports
 * cold-cache figures, so it clears this between runs.
 */
export function clearPmtilesCache() {
  archiveCache.clear();
  // Every benchmark run is cold: a recorded archive kept across runs would
  // serve the next run's tiles out of its directory cache.
  recordingArchives.clear();
}

export async function loadPmtilesInfo(filename) {
  const archive = getArchive(filename);
  const [header, metadata] = await Promise.all([
    archive.getHeader(),
    archive.getMetadata().catch(() => ({})),
  ]);

  const bounds = header
    ? [[header.minLon, header.minLat], [header.maxLon, header.maxLat]]
    : null;
  const center = header
    ? [(header.minLon + header.maxLon) / 2, (header.minLat + header.maxLat) / 2]
    : null;

  return {
    bounds,
    center,
    minZoom: header?.minZoom,
    maxZoom: header?.maxZoom,
    vectorLayers: Array.isArray(metadata?.vector_layers) ? metadata.vector_layers : [],
  };
}
