import { describe, expect, test } from 'vitest';
import { createExpression, featureFilter, validateStyleMin, v8 } from '@maplibre/maplibre-gl-style-spec';
import { buildFigureStyle, figureStyleKey } from './figureStyles';
import { buildDynamicStyle } from './dynamicStyle';
import figureColors from './figureColors.json';

// The viewer must color a dataset exactly like the paper figure of that dataset. The expected colors below are written out
// by hand from the official sources (USFWS NWI renderer, Geonovum BGT SLD, Swisstopo legend PDF) and from the Natural Earth
// convention table in bench/figures/ne_fig.py, so a typo in figureColors.json cannot make these tests pass by agreement with itself.

const POINT = 1, LINE = 2, POLYGON = 3;
const TYPE_NAME = { [POINT]: 'Point', [LINE]: 'LineString', [POLYGON]: 'Polygon' };

function hex(color) {
  const to = (v) => Math.round(v * 255).toString(16).padStart(2, '0');
  return `#${to(color.r)}${to(color.g)}${to(color.b)}`;
}
function evalProp(layer, group, prop, feature) {
  const spec = v8[`${group}_${layer.type}`][prop];
  const expr = createExpression(layer.paint[prop], spec);
  if (expr.result !== 'success') throw new Error(`${layer.id} ${prop}: ${JSON.stringify(expr.value)}`);
  return expr.value.evaluate({ zoom: 8 }, feature);
}
function passes(layer, feature) {
  if (!layer.filter) return true;
  return featureFilter(layer.filter).filter({ zoom: 8 }, feature);
}
/** What the viewer shows for one feature: the topmost layer of the given type that selects it (bottom-to-top draw order). */
function look(style, { sourceLayer, type, geom, props = {}, id }) {
  const feature = { type: geom, properties: props, id };
  const hit = style.layers.filter((l) => l.type === type && l['source-layer'] === sourceLayer && passes(l, feature)
    && (type !== 'fill' || evalProp(l, 'paint', 'fill-opacity', feature) > 0)
    && (type !== 'line' || evalProp(l, 'paint', 'line-width', feature) > 0));
  if (!hit.length) return null;
  const layer = hit[hit.length - 1];
  const key = { fill: 'fill-color', line: 'line-color', circle: 'circle-color' }[type];
  return { color: hex(evalProp(layer, 'paint', key, feature)), layer };
}
const style = (datasetId) => buildFigureStyle(datasetId, 'pmtiles://x/y.pmtiles', { isMlt: true });

describe('figureStyleKey', () => {
  test('recognises the four figure datasets, with or without overzoom suffix', () => {
    for (const id of ['usfws_luisiana_wetlands_geopackage', 'pdok_netherlands_infrostructure', 'natural_earth_vector', 'swisstopo_mountains_vector']) {
      expect(figureStyleKey(id)).toBe(id);
      expect(figureStyleKey(`${id}_oz2`)).toBe(id);
      expect(figureStyleKey(`${id}_oz4`)).toBe(id);
      expect(figureStyleKey(`${id}_sz2`)).toBe(id);
    }
  });
  test('anything else keeps the generic style', () => {
    expect(figureStyleKey('louisiana-260912')).toBeNull();
    expect(figureStyleKey(undefined)).toBeNull();
    expect(buildFigureStyle('louisiana-260912', 'pmtiles://x', {})).toBeNull();
  });
});

describe.each(['usfws_luisiana_wetlands_geopackage', 'pdok_netherlands_infrostructure', 'natural_earth_vector', 'swisstopo_mountains_vector'])('%s style', (id) => {
  test('is a valid MapLibre style on a white background, drawing the dataset source', () => {
    const s = style(id);
    expect(s.sources.dataset.encoding).toBe('mlt');
    expect(s.layers[0]).toMatchObject({ type: 'background', paint: { 'background-color': '#ffffff' } });
    const errors = validateStyleMin(s);
    expect(errors).toEqual([]);
    expect(s.layers.length).toBeGreaterThan(1);
    expect(s.layers.slice(1).every((l) => l.source === 'dataset')).toBe(true);
  });
  test('ends with a polygon fill layer, so the benchmark toggles a dense fill (pickToggleLayer takes the topmost fill)', () => {
    const s = style(id);
    expect(s.layers.some((l) => l.type === 'fill')).toBe(true);
  });
  test('uses no duplicate match labels (MapLibre rejects them)', () => {
    const dup = (e) => {
      if (!Array.isArray(e)) return;
      if (e[0] === 'match') {
        const labels = e.slice(2, -1).filter((_, i) => i % 2 === 0).flat();
        expect(new Set(labels).size).toBe(labels.length);
      }
      e.forEach(dup);
    };
    style(id).layers.forEach((l) => dup(l.paint));
  });
});

describe('USFWS wetlands: official NWI renderer colors', () => {
  const s = style('usfws_luisiana_wetlands_geopackage');
  const OFFICIAL = {
    'Freshwater Forested/Shrub Wetland': '#008737', 'Freshwater Emergent Wetland': '#7fc319', 'Freshwater Pond': '#678bc0',
    'Estuarine and Marine Wetland': '#66c2a5', Riverine: '#008fbf', Lake: '#12007c', 'Estuarine and Marine Deepwater': '#007c87',
  };
  test.each(Object.entries(OFFICIAL))('%s', (type, color) => {
    expect(look(s, { sourceLayer: 'hydrography', type: 'fill', geom: POLYGON, props: { WETLAND_TYPE: type } }).color).toBe(color);
  });
  test('a polygon with no wetland type is light gray, not an official color', () => {
    expect(look(s, { sourceLayer: 'hydrography', type: 'fill', geom: POLYGON, props: {} }).color).toBe('#d9d9d9');
  });
  test('unclassified polygons are drawn in a layer below the wetlands, so one that overlaps them cannot hide them', () => {
    // USFWS tiles contain an unclassified polygon that overlaps classified ones and comes late in the tile; MapLibre paints a
    // layer's features in tile order, so it has to live in its own layer underneath.
    const fills = s.layers.filter((l) => l.type === 'fill' && l['source-layer'] === 'hydrography');
    const classified = { type: POLYGON, properties: { WETLAND_TYPE: 'Lake' } };
    const unclassified = { type: POLYGON, properties: {} };
    const idxClassified = s.layers.indexOf(fills.find((l) => passes(l, classified)));
    const idxUnclassified = s.layers.indexOf(fills.find((l) => passes(l, unclassified)));
    expect(idxUnclassified).toBeGreaterThanOrEqual(0);
    expect(idxUnclassified).toBeLessThan(idxClassified);
    expect(fills.filter((l) => passes(l, classified)).length).toBe(1);       // each feature is painted by exactly one fill layer
    expect(fills.filter((l) => passes(l, unclassified)).length).toBe(1);
  });
  test('official outline gray', () => {
    expect(look(s, { sourceLayer: 'hydrography', type: 'line', geom: POLYGON, props: { WETLAND_TYPE: 'Lake' } }).color).toBe('#6e6e6e');
  });
  test('fills are opaque, so colors are not mixed with the background', () => {
    const l = look(s, { sourceLayer: 'hydrography', type: 'fill', geom: POLYGON, props: { WETLAND_TYPE: 'Lake' } }).layer;
    expect(evalProp(l, 'paint', 'fill-opacity', { type: POLYGON, properties: { WETLAND_TYPE: 'Lake' } })).toBe(1);
  });
});

describe('Netherlands BGT: official Geonovum colors', () => {
  const s = style('pdok_netherlands_infrostructure');
  const fill = (sourceLayer, props, geom = POLYGON) => look(s, { sourceLayer, type: 'fill', geom, props });
  test('land use', () => {
    expect(fill('land_use', { 'bgt-fysiekVoorkomen': 'groenvoorziening' }).color).toBe('#8ca800');
    expect(fill('land_use', { 'bgt-fysiekVoorkomen': 'grasland overig' }).color).toBe('#c9eb70');
    expect(fill('land_use', { 'bgt-fysiekVoorkomen': 'zand' }).color).toBe('#ffff99');
    expect(fill('land_use', { 'bgt-fysiekVoorkomen': 'erf' }).color).toBe('#ffffff');
  });
  test('water', () => {
    expect(fill('hydrography', { 'bgt-type': 'watervlakte' }).color).toBe('#bee8ff');
    expect(fill('hydrography', { 'bgt-type': 'waterloop' }).color).toBe('#73e9ff');
  });
  test('roads', () => {
    expect(fill('transportation', { 'bgt-functie': 'rijbaan regionale weg' }).color).toBe('#ffaa00');
    expect(fill('transportation', { 'bgt-functie': 'rijbaan autoweg' }).color).toBe('#e60000');
    expect(fill('transportation', { 'bgt-functie': 'voetpad' }).color).toBe('#ff9999');
  });
  test('a building without a class is the official pand red; a basin is light blue', () => {
    expect(fill('buildings', {}).color).toBe('#cc0000');
    expect(fill('buildings', { 'bgt-type': 'niet-bgt' }).color).toBe('#cc0000');
    expect(fill('buildings', { 'bgt-type': 'bassin' }).color).toBe('#BEE8FF'.toLowerCase());
  });
  test('functional-area barrier is a navy outline with no fill', () => {
    expect(fill('functioneelgebied', { 'bgt-type': 'kering' })).toBeNull();
    expect(look(s, { sourceLayer: 'functioneelgebied', type: 'line', geom: POLYGON, props: { 'bgt-type': 'kering' } }).color).toBe('#002750');
  });
  test('objects with no official color are neutral gray', () => {
    expect(look(s, { sourceLayer: 'infrastructure', type: 'circle', geom: POINT, props: { 'plus-type': 'lichtmast' } }).color).toBe('#535353');
    expect(look(s, { sourceLayer: 'infrastructure', type: 'line', geom: LINE, props: { 'plus-type': 'hek' } }).color).toBe('#000000');
  });
  test('rail is a dark line, drawn from the line geometry of the transportation layer', () => {
    expect(look(s, { sourceLayer: 'transportation', type: 'line', geom: LINE, props: { 'bgt-functie': 'trein' } }).color).toBe('#535353');
  });
  test('layers are drawn land use first and buildings above roads, as in the figure', () => {
    const idx = (sl, type) => s.layers.findIndex((l) => l['source-layer'] === sl && l.type === type);
    expect(idx('land_use', 'fill')).toBeLessThan(idx('hydrography', 'fill'));
    expect(idx('hydrography', 'fill')).toBeLessThan(idx('transportation', 'fill'));
    expect(idx('transportation', 'fill')).toBeLessThan(idx('buildings', 'fill'));
  });
});

describe('Natural Earth: figure convention colors', () => {
  const s = style('natural_earth_vector');
  test('ocean, land and urban area', () => {
    expect(look(s, { sourceLayer: 'hydrography', type: 'fill', geom: POLYGON, props: { featurecla: 'Ocean' } }).color).toBe('#b9d7ee');
    expect(look(s, { sourceLayer: 'land_use', type: 'fill', geom: POLYGON, props: { featurecla: 'Land' } }).color).toBe('#f3efe4');
    expect(look(s, { sourceLayer: 'land_use', type: 'fill', geom: POLYGON, props: { featurecla: 'Urban area' } }).color).toBe('#e2cfb4');
  });
  test('land is drawn above the ocean and lakes above land', () => {
    const idx = (sl, cls) => s.layers.findIndex((l) => l['source-layer'] === sl && l.type === 'fill' && passes(l, { type: POLYGON, properties: { featurecla: cls } }));
    expect(idx('hydrography', 'Ocean')).toBeLessThan(idx('land_use', 'Land'));
    expect(idx('land_use', 'Land')).toBeLessThan(idx('hydrography', 'Lake'));
  });
  test('roads by importance (type for roads, featurecla for rail)', () => {
    const line = (props) => look(s, { sourceLayer: 'transportation', type: 'line', geom: LINE, props }).color;
    expect(line({ type: 'Freeway' })).toBe('#d94f30');
    expect(line({ type: 'Major Highway', featurecla: 'Road' })).toBe('#d94f30');
    expect(line({ type: 'Secondary' })).toBe('#f4d03f');
    expect(line({ type: 'Primary' })).toBe('#f0a030');
    expect(line({ featurecla: 'Railroad' })).toBe('#555555');
    expect(line({ type: 'Ferry' })).toBe('#7e57c2');
  });
  test('ports and airports are dots', () => {
    expect(look(s, { sourceLayer: 'transportation', type: 'circle', geom: POINT, props: { featurecla: 'Airport', type: 'major' } }).color).toBe('#2e7d32');
    expect(look(s, { sourceLayer: 'transportation', type: 'circle', geom: POINT, props: { featurecla: 'Port' } }).color).toBe('#1f4e79');
  });
  test('administrative levels share a look by prefix, in upper-case or lower-case attribute names', () => {
    const edge = (props) => look(s, { sourceLayer: 'boundaries', type: 'line', geom: POLYGON, props }).color;
    expect(edge({ featurecla: 'Admin-0 country' })).toBe('#222222');
    expect(edge({ FEATURECLA: 'Admin-0 scale ranks' })).toBe('#222222');
    expect(edge({ featurecla: 'Admin-1 states provinces' })).toBe('#8e5ea2');
    expect(edge({ featurecla: 'Admin-2 scale rank' })).toBe('#b5b5b5');
  });
  test('admin polygons are outlines only: no fill hides the map below', () => {
    expect(look(s, { sourceLayer: 'boundaries', type: 'fill', geom: POLYGON, props: { featurecla: 'Admin-0 country' } })).toBeNull();
  });
  test('a class with no defined color falls back to a gray outline instead of disappearing', () => {
    expect(look(s, { sourceLayer: 'land_use', type: 'line', geom: POLYGON, props: { featurecla: 'Something New' } }).color).toBe('#9a9a9a');
  });
});

describe('Swisstopo: official legend colors by rock unit, resolved through the feature id', () => {
  const s = style('swisstopo_mountains_vector');
  const OFFICIAL = { Sr: '#7cccbf', HK: '#c7c989', Pf: '#cbd8d2', K2: '#d1e173', Db: '#d3d5b8', Oe: '#83c994', M: '#8dd8f8', D: '#8db4ca', L: '#c5a8d0',
    Tr: '#fec54e', P: '#fbb781', T: '#fff57c', UH1: '#b3ddc6', Q: '#fff8e6', "USM'": '#fdd2b9' };
  const idOf = (unit) => {
    const ids = JSON.parse(JSON.stringify(figureColors.swisstopo_mountains_vector.colors[OFFICIAL[unit]]));
    return ids[0];
  };
  test.each(Object.keys(OFFICIAL))('unit %s', (unit) => {
    // the table is keyed by color; every id listed under a unit's color must come out in that color
    const id = idOf(unit);
    expect(look(s, { sourceLayer: 'terrain', type: 'fill', geom: POLYGON, props: {}, id }).color).toBe(OFFICIAL[unit]);
  });
  test('all 214 feature ids of the dataset are covered, each exactly once', () => {
    const all = Object.values(figureColors.swisstopo_mountains_vector.colors).flat();
    expect(all.length).toBe(214);
    expect(new Set(all).size).toBe(214);
  });
  test('an id outside the table is drawn white rather than failing', () => {
    expect(look(s, { sourceLayer: 'terrain', type: 'fill', geom: POLYGON, props: {}, id: 999999 }).color).toBe('#ffffff');
  });
});

describe('integration with buildDynamicStyle', () => {
  const PM = 'pmtiles://http://localhost/data/output/x.pmtiles';
  test('a figure dataset gets the figure style, keeping label layers', () => {
    const layers = [{ id: 'hydrography', geometry_type: 'MultiPolygon', fields: ['WETLAND_TYPE'] }];
    const st = buildDynamicStyle(PM, layers, { datasetId: 'usfws_luisiana_wetlands_geopackage', protocolLayers: layers.map((l) => ({ name: l.id, geometry_type: l.geometry_type, fields: l.fields })) });
    expect(st.layers[0].paint['background-color']).toBe('#ffffff');
    expect(st.layers.some((l) => String(l.id).startsWith('figure-'))).toBe(true);
    expect(st.layers.every((l) => !/-fill$/.test(l.id) || String(l.id).startsWith('figure-'))).toBe(true);
    expect(validateStyleMin(st)).toEqual([]);
  });
  test('any other dataset keeps the generic style, unchanged', () => {
    const st = buildDynamicStyle(PM, [{ id: 'wetlands', geometry_type: 'polygon' }], { datasetId: 'something_else' });
    expect(st.layers[0].paint['background-color']).toBe('#eef2e6');
    expect(st.layers.some((l) => l.id === 'wetlands-fill')).toBe(true);
  });
});
