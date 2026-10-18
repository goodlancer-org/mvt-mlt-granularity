/**
 * A ledger of every tile the renderer actually received, kept on the main thread.
 *
 * Resource Timing cannot see MBTiles traffic. MapLibre fetches ordinary vector
 * tile URLs from its worker pool, and a worker's resource entries land in the
 * worker's own performance timeline, not the window's. PMTiles was visible only
 * because `addProtocol` handlers run on the main thread — which is why every
 * MBTiles byte and request figure in the GeoCover benchmark read zero while the
 * PMTiles ones read true.
 *
 * Both containers are therefore routed through recording protocol handlers and
 * counted here, so the two are measured the same way. This also excludes the
 * PMTiles header and directory fetches that Resource Timing was counting as
 * tile bytes.
 */

const records = [];

/**
 * Note that the renderer asked for a tile. Called from the protocol handlers.
 *
 * The request is recorded when it is made, not when it completes, because
 * `*_new_tile_requests` counts requests generated during a phase. The returned
 * record is filled in with the byte count once the tile arrives; a request that
 * fails or is aborted keeps its zero and still counts as a request.
 */
export function recordTileRequest(url) {
  const record = { url, byteLength: 0, at: performance.now() };
  records.push(record);
  return record;
}

/** Attach the delivered size to a request recorded earlier. */
export function recordTileBytes(record, byteLength) {
  if (record) record.byteLength = byteLength;
}

/**
 * The size of a tile body, whatever container it came from.
 *
 * PMTiles hands back a Uint8Array and the MBTiles handler an ArrayBuffer, so a
 * check for one of those alone silently counts the other as no traffic at all.
 */
export function tileByteLength(data) {
  if (data instanceof ArrayBuffer) return data.byteLength;
  if (ArrayBuffer.isView(data)) return data.byteLength;
  return 0;
}

/**
 * The bytes that crossed the network for a tile.
 *
 * The paper defines the byte metrics as tile data *transferred*, and tiles are
 * stored gzipped in both containers. Both delivery paths inflate a tile before
 * MapLibre sees it — `fetch` does it for the MBTiles handler because the API
 * sends `Content-Encoding: gzip`, and the PMTiles library does it internally —
 * so the body handed to the renderer is several times what was downloaded.
 * The reported length is preferred and the inflated body is the fallback.
 */
export function wireByteLength(contentLength, data) {
  const reported = Number.parseInt(contentLength, 10);
  return Number.isFinite(reported) ? reported : tileByteLength(data);
}

/** Note one tile delivered to the renderer, request and bytes in one call. */
export function recordTile(url, byteLength) {
  recordTileBytes(recordTileRequest(url), byteLength);
}

/** Drop everything recorded. Called once at the start of each benchmark run. */
export function resetTileTraffic() {
  records.length = 0;
}

/** A boundary between phases. */
export function tileTrafficMark() {
  return records.length;
}

/** Everything recorded since a mark. */
export function tileTrafficSince(mark) {
  return records.slice(mark);
}

export function sumTileTrafficBytes(slice) {
  return slice.reduce((total, r) => total + r.byteLength, 0);
}

export function countTileTraffic(slice) {
  return slice.length;
}
