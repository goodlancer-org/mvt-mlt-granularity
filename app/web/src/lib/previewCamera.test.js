import { describe, expect, test } from 'vitest';
import { isWorldBounds, pickPreviewCamera } from './previewCamera';

const ZOOM = { minZoom: 0, maxZoom: 14, initialZoom: 1 };
const WORLD = [[-180, -85.0511287], [180, 85.0511287]];
const NIJMEGEN = [[5.405, 51.795], [6.042, 51.917]];

describe('isWorldBounds', () => {
  test('the header of an archive converted without an extent is the world', () => {
    expect(isWorldBounds(WORLD)).toBe(true);
  });
  test.each([
    ['Natural Earth', [[-97, 30], [-70, 47]]],
    ['Louisiana wetlands', [[-90.35, 29.35], [-89.95, 29.75]]],
    ['Swisstopo', [[9.15, 47.05], [9.5, 47.3]]],
    ['a whole continent', [[-25, 34], [45, 72]]],
  ])('%s is a real extent', (_name, bounds) => {
    expect(isWorldBounds(bounds)).toBe(false);
  });
  test('missing or malformed bounds are not the world', () => {
    expect(isWorldBounds(null)).toBe(false);
    expect(isWorldBounds(undefined)).toBe(false);
    expect(isWorldBounds([])).toBe(false);
  });
});

describe('pickPreviewCamera', () => {
  test('an archive whose header says the world opens on the dataset extent, zoomed to fit', () => {
    const camera = pickPreviewCamera({ headerBounds: WORLD, headerCenter: [0, 0], extentBounds: NIJMEGEN, zoomRange: ZOOM });

    expect(camera.bounds).toEqual(NIJMEGEN);
    expect(camera.center[0]).toBeCloseTo(5.7235, 4);
    expect(camera.center[1]).toBeCloseTo(51.856, 3);
    expect(camera.fitMaxZoom).toBe(14);                // the overview cap (zoom 3) would show no polygons of this dataset
    expect(camera.source).toBe('dataset-extent');
  });

  test('an archive with a real header keeps exactly the camera it always had', () => {
    const header = [[9.15, 47.05], [9.5, 47.3]];
    const camera = pickPreviewCamera({ headerBounds: header, headerCenter: [9.325, 47.175], extentBounds: [[1, 1], [2, 2]], zoomRange: ZOOM });

    expect(camera.bounds).toEqual(header);
    expect(camera.center).toEqual([9.325, 47.175]);
    expect(camera.fitMaxZoom).toBe(3);                 // min(maxZoom, initialZoom + 2): the existing overview cap
    expect(camera.source).toBe('archive-header');
  });

  test('a world header with no dataset extent changes nothing', () => {
    const camera = pickPreviewCamera({ headerBounds: WORLD, headerCenter: [0, 0], extentBounds: null, zoomRange: ZOOM });

    expect(camera.bounds).toEqual(WORLD);
    expect(camera.center).toEqual([0, 0]);
    expect(camera.fitMaxZoom).toBe(3);
  });

  test('no header at all falls back to the dataset extent with the usual cap', () => {
    const camera = pickPreviewCamera({ headerBounds: null, headerCenter: null, extentBounds: NIJMEGEN, zoomRange: ZOOM });

    expect(camera.bounds).toEqual(NIJMEGEN);
    expect(camera.fitMaxZoom).toBe(3);
  });

  test('the overview cap never exceeds the archive maximum zoom', () => {
    const camera = pickPreviewCamera({ headerBounds: [[0, 0], [1, 1]], headerCenter: [0.5, 0.5], extentBounds: null, zoomRange: { maxZoom: 2, initialZoom: 1 } });

    expect(camera.fitMaxZoom).toBe(2);
  });
});
