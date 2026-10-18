/**
 * Where the map preview opens.
 *
 * An archive header normally says where its data is. A conversion that was not given an extent writes the whole world and a (0, 0)
 * center instead (the Netherlands archives did), and a preview that trusts it opens on empty ocean. For such an archive the dataset's
 * extent, which the API reads from the archive's tile directory, is used instead, and the preview zooms to fit it: the usual
 * "overview" cap (a few zoom levels above the archive's minimum) would stop at a zoom where this data has no content yet.
 *
 * Every other archive keeps exactly the camera it always had, so the render benchmark compares like with like.
 */

const WORLD_LON_SPAN = 350;
const WORLD_LAT_SPAN = 150;

/** True for bounds that cover (nearly) the whole world, i.e. the header carries no information about where the data is. */
export function isWorldBounds(bounds) {
  if (!Array.isArray(bounds) || bounds.length !== 2) return false;
  const [[west, south], [east, north]] = bounds;
  return east - west >= WORLD_LON_SPAN && north - south >= WORLD_LAT_SPAN;
}

function centerOf(bounds) {
  const [[west, south], [east, north]] = bounds;
  return [(west + east) / 2, (south + north) / 2];
}

/**
 * @param {object} input
 * @param {number[][]|null} input.headerBounds   [[w, s], [e, n]] from the archive header, already in degrees
 * @param {number[]|null}   input.headerCenter   [lon, lat] from the archive header
 * @param {number[][]|null} input.extentBounds   [[w, s], [e, n]] from the dataset protocol, already in degrees
 * @param {{maxZoom: number, initialZoom: number}} input.zoomRange
 * @returns {{bounds: number[][]|null, center: number[]|null, fitMaxZoom: number, source: string}}
 */
export function pickPreviewCamera({ headerBounds, headerCenter, extentBounds, zoomRange }) {
  const overviewZoom = Math.min(zoomRange.maxZoom, zoomRange.initialZoom + 2);

  if (isWorldBounds(headerBounds) && extentBounds) {
    return { bounds: extentBounds, center: centerOf(extentBounds), fitMaxZoom: zoomRange.maxZoom, source: 'dataset-extent' };
  }
  return {
    bounds: headerBounds || extentBounds || null,
    center: headerCenter || null,
    fitMaxZoom: overviewZoom,
    source: headerBounds ? 'archive-header' : 'dataset-extent',
  };
}
