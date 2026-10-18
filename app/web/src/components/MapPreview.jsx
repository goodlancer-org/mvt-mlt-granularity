import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { initMaplibre, loadPmtilesInfo, pmtilesUrl } from '../lib/pmtiles';
import { detectSchema, detectLocale } from '../lib/schemaDetector';
import { buildMapStyle } from '../lib/mapStyle';
import { buildDynamicStyle } from '../lib/dynamicStyle';
import { pickPreviewCamera } from '../lib/previewCamera';
import './MapPreview.css';

function baseName(path) {
  if (!path) return '';
  return path.split(/[\\/]/).pop();
}

function isFiniteNumber(value) {
  return Number.isFinite(Number(value));
}

function webMercatorToWgs84(x, y) {
  const R = 6378137;
  const lon = (x / R) * (180 / Math.PI);
  const lat = (Math.atan(Math.exp(y / R)) * 2 - Math.PI / 2) * (180 / Math.PI);
  return [lon, lat];
}

function normalizeBounds(bounds) {
  if (!Array.isArray(bounds) || bounds.length !== 2) return null;
  const sw = bounds[0];
  const ne = bounds[1];
  if (!Array.isArray(sw) || !Array.isArray(ne) || sw.length < 2 || ne.length < 2) return null;

  let minX = Number(sw[0]);
  let minY = Number(sw[1]);
  let maxX = Number(ne[0]);
  let maxY = Number(ne[1]);

  if (![minX, minY, maxX, maxY].every(Number.isFinite)) return null;

  const looksLikeMercator =
    Math.max(Math.abs(minX), Math.abs(maxX)) > 180 ||
    Math.max(Math.abs(minY), Math.abs(maxY)) > 90;

  if (looksLikeMercator) {
    [minX, minY] = webMercatorToWgs84(minX, minY);
    [maxX, maxY] = webMercatorToWgs84(maxX, maxY);
  }

  const lonMin = Math.min(minX, maxX);
  const lonMax = Math.max(minX, maxX);
  const latMin = Math.max(-85.0511, Math.min(minY, maxY));
  const latMax = Math.min(85.0511, Math.max(minY, maxY));

  if (!Number.isFinite(lonMin) || !Number.isFinite(lonMax) || !Number.isFinite(latMin) || !Number.isFinite(latMax)) {
    return null;
  }
  if (lonMin === lonMax || latMin === latMax) return null;

  return [[lonMin, latMin], [lonMax, latMax]];
}

function boundsFromProtocolExtent(protocol) {
  const extent = protocol?.dataset?.extent;
  if (!Array.isArray(extent) || extent.length < 4) return null;
  const [minX, minY, maxX, maxY] = extent;
  if (![minX, minY, maxX, maxY].every(isFiniteNumber)) return null;
  return normalizeBounds([
    [Number(minX), Number(minY)],
    [Number(maxX), Number(maxY)],
  ]);
}

function normalizeCenter(center) {
  if (!Array.isArray(center) || center.length < 2) return null;
  const lon = Number(center[0]);
  const lat = Number(center[1]);
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  return [lon, lat];
}

function resolveZoomRange(protocol, pmtilesInfo) {
  const topoMin = Number(protocol?.topology?.min_zoom);
  const topoMax = Number(protocol?.topology?.max_zoom);
  const pmMin = Number(pmtilesInfo?.minZoom ?? pmtilesInfo?.minzoom);
  const pmMax = Number(pmtilesInfo?.maxZoom ?? pmtilesInfo?.maxzoom);

  const minZoom = Number.isFinite(pmMin)
    ? pmMin
    : Number.isFinite(topoMin)
      ? topoMin
      : 0;

  const rawMaxZoom = Number.isFinite(pmMax)
    ? pmMax
    : Number.isFinite(topoMax)
      ? topoMax
      : 14;

  const maxZoom = Math.max(minZoom + 1, rawMaxZoom);
  const initialZoom = Math.min(maxZoom, Math.max(minZoom, minZoom + 1));

  return { minZoom, maxZoom, initialZoom };
}

export default function MapPreview({ protocol, encoding = 'mlt' }) {
  const mapContainer = useRef(null);
  const mapRef = useRef(null);
  const [loaded, setLoaded] = useState(false);
  const [previewError, setPreviewError] = useState('');

  useEffect(() => {
    if (!protocol || !mapContainer.current) return undefined;
    setLoaded(false);
    setPreviewError('');
    initMaplibre();

    let cancelled = false;
    let map = null;
    let loadTimer = null;

    const failPreview = (message) => {
      if (cancelled) return;
      setPreviewError(message);
      setLoaded(false);
    };

    const run = async () => {
      const output = protocol.outputs?.[encoding] || protocol.outputs?.mlt || protocol.outputs?.mvt;
      if (!output?.path) {
        failPreview(`No ${encoding.toUpperCase()} archive path is present in protocol outputs.`);
        return;
      }
      const declaredTileCount = Number(output.tile_count);
      if (Number.isFinite(declaredTileCount) && declaredTileCount <= 0) {
        failPreview(
          `${encoding.toUpperCase()} preview is unavailable: archive has 0 tiles according to protocol summary.`
        );
        return;
      }

      const filename = baseName(output.path);
      const locale = detectLocale(protocol.dataset?.title || protocol.dataset?.id);
      const sourceUrl = pmtilesUrl(filename);
      let pmtilesInfo = null;
      try {
        pmtilesInfo = await loadPmtilesInfo(filename);
      } catch (error) {
        const details = error?.message ? ` ${error.message}` : '';
        failPreview(`Failed to read PMTiles header/metadata for ${filename}.${details}`);
        return;
      }
      const vectorLayers = pmtilesInfo?.vectorLayers || [];
      const schema = detectSchema(vectorLayers);
      const isMlt = encoding === 'mlt';
      const zoomRange = resolveZoomRange(protocol, pmtilesInfo);
      // An archive converted without an extent says "the whole world" in its header; pickPreviewCamera then uses the dataset's own
      // extent. Archives with a real header keep their camera unchanged.
      const camera = pickPreviewCamera({
        headerBounds: normalizeBounds(pmtilesInfo?.bounds),
        headerCenter: normalizeCenter(pmtilesInfo?.center),
        extentBounds: boundsFromProtocolExtent(protocol),
        zoomRange,
      });
      const initialBounds = camera.bounds;
      const initialCenter = camera.center;

      const addressedTiles = Number(pmtilesInfo?.addressedTilesCount ?? pmtilesInfo?.tileCount);
      if (Number.isFinite(addressedTiles) && addressedTiles <= 0) {
        failPreview(`${encoding.toUpperCase()} preview is unavailable: PMTiles reports 0 addressed tiles.`);
        return;
      }

      const style = schema === 'openmaptiles'
        ? await buildMapStyle(sourceUrl, { locale, isMlt })
        : buildDynamicStyle(sourceUrl, vectorLayers, {
            isMlt,
            datasetId: protocol.dataset?.id,
            protocolLayers: protocol.layer_summary || [],
            minLabelZoom: Math.min(8, Math.max(4, zoomRange.minZoom + 1)),
          });

      if (cancelled) return;
      map = new maplibregl.Map({
        container: mapContainer.current,
        style,
        center: initialCenter || [0, 0],
        zoom: zoomRange.initialZoom,
        minZoom: zoomRange.minZoom,
        maxZoom: zoomRange.maxZoom,
        renderWorldCopies: false,
      });
      map.addControl(new maplibregl.NavigationControl(), 'top-right');

      map.on('error', (event) => {
        const mapError = event?.error;
        const details = mapError?.message || 'MapLibre failed to load one or more resources.';
        failPreview(`Preview failed for ${filename}: ${details}`);
      });

      map.on('load', () => {
        if (loadTimer) {
          clearTimeout(loadTimer);
          loadTimer = null;
        }
        if (initialBounds) {
          map.fitBounds(initialBounds, {
            padding: 40,
            duration: 0,
            maxZoom: camera.fitMaxZoom,
          });
        } else if (initialCenter) {
          map.jumpTo({
            center: initialCenter,
            zoom: Math.min(
              zoomRange.maxZoom,
              Math.max(zoomRange.minZoom, Number(pmtilesInfo?.minZoom ?? zoomRange.initialZoom)),
            ),
          });
        }
        setPreviewError('');
        setLoaded(true);
      });

      loadTimer = setTimeout(() => {
        failPreview(
          `Timed out while loading preview for ${filename}. Check browser console and /data/output availability.`
        );
      }, 15000);

      mapRef.current = map;
    };

    run().catch((error) => {
      const details = error?.message ? ` ${error.message}` : '';
      failPreview(`Failed to initialize map preview.${details}`);
      console.error('Failed to initialize map preview', error);
    });

    return () => {
      cancelled = true;
      if (loadTimer) {
        clearTimeout(loadTimer);
      }
      if (map) map.remove();
    };
  }, [protocol, encoding]);

  return (
    <div className="map-preview">
      {!loaded ? (
        <div className="map-measuring-overlay">
          {previewError || 'Loading preview…'}
        </div>
      ) : null}
      <div ref={mapContainer} className="map-container" />
    </div>
  );
}
