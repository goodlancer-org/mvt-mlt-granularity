/**
 * Figure-parity styles: color the four study datasets exactly like their paper figures.
 *
 * The colors are not decided here. bench/figures/export_web_styles.py reads the figure scripts (the single source of truth:
 * official USFWS NWI / Geonovum BGT / Swisstopo legend colors, plus the Natural Earth convention) and writes figureColors.json;
 * this module only turns those rules into MapLibre layers. Regenerate the JSON after changing a figure script.
 *
 * Differences from the paper figure that MapLibre forces on us:
 *  - hatch patterns (BGT forest, orchard, ...) need sprite images; they are drawn as the pattern color at 30% opacity;
 *  - line widths are in screen pixels and grow with zoom instead of being fixed to the 4096-unit tile grid.
 */
import figureColors from './figureColors.json';

const SOURCE = 'dataset';
const GRAY = '#535353';                      // the figure draws white lines/points dark gray
const TRANSPARENT = 'rgba(0,0,0,0)';
// Expression-form geometry filters. The legacy ['==', '$type', ...] form must not be mixed with the expression-form class filters
// below: MapLibre would parse the whole filter as legacy and reject it.
const geometryIn = (...types) => ['in', ['geometry-type'], ['literal', types]];
const POLYGON = geometryIn('Polygon', 'MultiPolygon');
const LINE = geometryIn('LineString', 'MultiLineString');
const POINT = geometryIn('Point', 'MultiPoint');

/** The figure dataset a protocol dataset id belongs to (overzoom variants '..._oz2' and structural '..._sz2' use the same colors), or null. */
export function figureStyleKey(datasetId) {
  if (!datasetId) return null;
  const base = String(datasetId).replace(/_(oz|sz)\d+$/i, '');
  return Object.prototype.hasOwnProperty.call(figureColors, base) ? base : null;
}

function kindOf(rule) {
  const h = rule.hatch;
  if (!h) return 'solid';
  if (h === 'pt') return 'point';
  if (h.startsWith('line')) return 'line';
  return 'pattern';
}

/** How one class is drawn for each geometry type, from its {fill, edge, hatch} rule. */
function look(rule) {
  const kind = kindOf(rule);
  const w = /^line:([0-9.]+)/.exec(rule.hatch || '');
  const stroke = rule.edge === '#ffffff' ? GRAY : rule.edge;
  return {
    kind,
    fillColor: kind === 'solid' ? rule.fill : kind === 'pattern' ? rule.edge : TRANSPARENT,
    fillOpacity: kind === 'solid' ? 1 : kind === 'pattern' ? 0.3 : 0,
    outlineColor: rule.edge,
    outlineWidth: kind === 'line' ? (w ? Number(w[1]) : 1.0) : kind === 'point' ? 0 : 0.3,
    lineColor: stroke,
    lineWidth: kind === 'point' ? 0 : kind === 'line' && w ? Number(w[1]) : 0.7,
    pointColor: stroke,
  };
}

/** `match` over the class expression; classes with the same output share one arm. Falls back to `dflt`. */
function matchBy(classExpr, rules, pick, dflt) {
  const arms = new Map();
  for (const r of rules) {
    const out = pick(r);
    const k = JSON.stringify(out);
    if (!arms.has(k)) arms.set(k, { out, keys: [] });
    arms.get(k).keys.push(r.key);
  }
  if (!arms.size || !classExpr) return dflt;
  const expr = ['match', classExpr];
  for (const { out, keys } of arms.values()) expr.push(keys.length === 1 ? keys[0] : keys, out);
  expr.push(dflt);
  return expr;
}

/** Widths grow with zoom; the zoom interpolation has to be the outermost expression, so the class match goes inside each stop. */
function widthExpr(classExpr, rules, pick, dflt) {
  const at = (k) => matchBy(classExpr, rules, (r) => pick(r) * k, dflt * k);
  return ['interpolate', ['linear'], ['zoom'], 4, at(0.7), 14, at(1.8)];
}

/** Style layers (fill, polygon outline, line, point) for one source layer and one z-level of classes. */
function entryLayers(entry, n, pointRadius = 1) {
  const rules = entry.rules.map((r) => ({ key: r.key, ...look(r) }));
  const def = entry.default ? look(entry.default) : null;
  const cls = entry.classExpr;
  const all = def ? [def, ...rules] : rules;
  const keys = rules.map((r) => r.key);
  let classFilter = null;
  if (entry.notIn) classFilter = ['!', ['in', cls, ['literal', entry.notIn]]];
  else if (!def && keys.length) classFilter = ['in', cls, ['literal', keys]];
  const geom = (g) => (classFilter ? ['all', g, classFilter] : g);
  const pickD = (pick, fallback) => (def ? pick(def) : fallback);
  const base = { source: SOURCE, 'source-layer': entry.sourceLayer };
  const id = (suffix) => `figure-${entry.sourceLayer}-${n}-${suffix}`;
  const out = [];

  if (all.some((l) => l.kind === 'solid' || l.kind === 'pattern')) {
    out.push({
      ...base, id: id('fill'), type: 'fill', filter: geom(POLYGON),
      paint: {
        'fill-color': matchBy(cls, rules, (r) => r.fillColor, pickD((l) => l.fillColor, TRANSPARENT)),
        'fill-opacity': matchBy(cls, rules, (r) => r.fillOpacity, pickD((l) => l.fillOpacity, 0)),
      },
    });
  }
  if (all.some((l) => l.outlineWidth > 0)) {
    out.push({
      ...base, id: id('outline'), type: 'line', filter: geom(POLYGON),
      paint: {
        'line-color': matchBy(cls, rules, (r) => r.outlineColor, pickD((l) => l.outlineColor, TRANSPARENT)),
        'line-width': widthExpr(cls, rules, (r) => r.outlineWidth, pickD((l) => l.outlineWidth, 0)),
      },
    });
  }
  if (all.some((l) => l.lineWidth > 0)) {
    out.push({
      ...base, id: id('line'), type: 'line', filter: geom(LINE),
      paint: {
        'line-color': matchBy(cls, rules, (r) => r.lineColor, pickD((l) => l.lineColor, TRANSPARENT)),
        'line-width': widthExpr(cls, rules, (r) => r.lineWidth, pickD((l) => l.lineWidth, 0)),
      },
    });
  }
  out.push({
    ...base, id: id('point'), type: 'circle', filter: geom(POINT),
    paint: {
      'circle-color': matchBy(cls, rules, (r) => r.pointColor, pickD((l) => l.pointColor, TRANSPARENT)),
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, pointRadius * 0.6, 14, pointRadius * 1.5],
    },
  });
  return out;
}

/** Swisstopo: the tiles carry no attributes, so the rock unit comes from the feature id (id -> unit -> official legend color). */
function idLayers(spec) {
  const arms = [];
  for (const [color, ids] of Object.entries(spec.colors)) arms.push(ids, color);
  const base = { source: SOURCE, 'source-layer': spec.sourceLayer };
  return [
    {
      ...base, id: `figure-${spec.sourceLayer}-fill`, type: 'fill', filter: POLYGON,
      paint: { 'fill-color': ['match', ['coalesce', ['id'], -1], ...arms, spec.default], 'fill-opacity': 1 },
    },
    {
      ...base, id: `figure-${spec.sourceLayer}-outline`, type: 'line', filter: POLYGON,
      paint: { 'line-color': spec.edge, 'line-width': ['interpolate', ['linear'], ['zoom'], 4, 0.2, 14, 0.6] },
    },
  ];
}

/**
 * Features with no (or an unknown) class and an unofficial look go in their own layer *below* the classified ones, as in the figures.
 * MapLibre paints a layer's features in tile order, so one unclassified polygon that overlaps the classified ones (USFWS has such
 * polygons) would otherwise land on top and hide them.
 */
function splitUnderlay(entry) {
  if (!entry.default || !entry.defaultUnder || !entry.rules.length) return [entry];
  const keys = entry.rules.map((r) => r.key);
  return [{ ...entry, rules: [], notIn: keys }, { ...entry, default: null }];
}

/** Ordered layers (bottom first) and background for a figure dataset, or null for any other dataset. */
export function figureStyleLayers(key) {
  const spec = key ? figureColors[key] : null;
  if (!spec) return null;
  const layers = spec.kind === 'id' ? idLayers(spec) : spec.layers.flatMap(splitUnderlay).flatMap((e, n) => entryLayers(e, n, spec.pointRadius));
  return { background: spec.background, layers };
}

/** A complete MapLibre style for a figure dataset, or null. */
export function buildFigureStyle(datasetId, pmtilesUrl, options = {}) {
  const { isMlt = true, tilesUrl = null } = options;
  const parts = figureStyleLayers(figureStyleKey(datasetId));
  if (!parts) return null;
  const source = tilesUrl
    ? { type: 'vector', tiles: [tilesUrl] }
    : { type: 'vector', url: pmtilesUrl.startsWith('pmtiles://') ? pmtilesUrl : `pmtiles://${pmtilesUrl}` };
  if (isMlt) source.encoding = 'mlt';
  return {
    version: 8,
    sources: { [SOURCE]: source },
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': parts.background } }, ...parts.layers],
  };
}
