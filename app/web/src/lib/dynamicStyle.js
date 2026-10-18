/**
 * Dynamic style builder for non-OpenMapTiles datasets.
 * Creates a reasonable visualization for arbitrary vector tile schemas
 * with automatic layer ordering and label support.
 */

import { figureStyleKey, figureStyleLayers } from './figureStyles';

// Color palettes by geometry type for visual distinction
const FILL_COLORS = [
  '#4f8ff7', '#3dd68c', '#f5a623', '#e5534b',
  '#a855f7', '#06b6d4', '#f43f5e', '#84cc16',
];

const LINE_COLORS = [
  '#60a5fa', '#34d399', '#fbbf24', '#f87171',
  '#c084fc', '#22d3ee', '#fb7185', '#a3e635',
];

const POINT_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16',
];

const OSM_TYPE_FIELD_CANDIDATES = [
  'highway', 'waterway', 'landuse', 'natural', 'place', 'boundary',
  'type', 'featurecla', 'fclass', 'class', 'kind', 'category',
];

// Common attribute names that might contain labels (case-insensitive patterns)
// Order matters: more specific patterns first
const LABEL_PATTERNS = [
  /^name$/i,                    // exact "name"
  /^label$/i,                   // exact "label"
  /^title$/i,                   // exact "title"
  /^description$/i,             // "DESCRIPTION" (geology, bedrock)
  /^german$/i,                  // "GERMAN" (Swiss geological lookup tables)
  /^french$/i,                  // "FRENCH" (Swiss geological lookup tables)
  /^display_?name$/i,           // displayname or display_name
  /unit_?name$/i,               // assessmentunitname, unitname, unit_name
  /feature_?name$/i,            // featurename, feature_name
  /object_?name$/i,             // objectname, object_name
  /street_?name$/i,             // streetname, street_name
  /place_?name$/i,              // placename, place_name
  /water_?body/i,               // waterbody, water_body (for water features)
  /^more_?info$/i,              // "MORE_INFO" (geological descriptive text)
  /_name$/i,                    // ends with '_name' (e.g. TTEC_NAME, LTYP_NAME)
  // NOTE: /^kind$/ and /^symbol$/ are intentionally excluded - they are numeric codes
];

// Fields to exclude from label detection (administrative/metadata fields)
const EXCLUDE_FROM_LABELS = [
  /^organization/i,             // organizationname, organizationid
  /^state$/i,                   // state code/name
  /^region$/i,                  // region
  /^country/i,                  // country
  /^submissionid$/i,
  /^permid/i,
  /type$/i,                     // *type fields
  /^crs$/i,
  /^id$/i,
  /identifier$/i,               // *identifier
  /joinkey$/i,                  // *joinkey
  /^kind$/i,                    // KIND is numeric code, not label
  /^symbol$/i,                  // SYMBOL is numeric code (geolcode), not label
  /^geolcode$/i,                // GEOLCODE is numeric lookup code
  /^code$/i,                    // Generic code fields
];

function hasField(fields, candidates) {
  if (!Array.isArray(fields) || fields.length === 0) return false;
  const names = fields.map((f) => (typeof f === 'string' ? f : f?.name)).filter(Boolean);
  return candidates.some((candidate) => names.some((name) => name.toLowerCase() === candidate.toLowerCase()));
}

function fieldNames(fields) {
  if (!Array.isArray(fields)) return [];
  return fields.map((f) => (typeof f === 'string' ? f : f?.name)).filter(Boolean);
}

function resolveTypeField(protoInfo) {
  const names = fieldNames(protoInfo?.fields);
  const byLower = new Map(names.map((name) => [name.toLowerCase(), name]));
  const semanticType = String(protoInfo?.semantic_type || '').trim();
  if (semanticType && semanticType.toLowerCase() !== 'unknown') {
    const matched = byLower.get(semanticType.toLowerCase());
    if (matched) return matched;
    return semanticType;
  }

  for (const candidate of OSM_TYPE_FIELD_CANDIDATES) {
    const matched = byLower.get(candidate.toLowerCase());
    if (matched) return matched;
  }
  return null;
}

function typeTokenExpression(typeField) {
  if (!typeField) return '';
  return ['downcase', ['coalesce', ['to-string', ['get', typeField]], '']];
}

function osmTransportLineColor(typeField, fallback) {
  const token = typeTokenExpression(typeField);
  if (!token) return fallback;
  return [
    'match',
    token,
    'motorway', '#df7366',
    'motorway_link', '#df7366',
    'trunk', '#e39b64',
    'trunk_link', '#e39b64',
    'primary', '#f0c06d',
    'primary_link', '#f0c06d',
    'secondary', '#f7e188',
    'secondary_link', '#f7e188',
    'tertiary', '#f4f0a8',
    'tertiary_link', '#f4f0a8',
    'residential', '#ffffff',
    'unclassified', '#e9e4d6',
    'service', '#ddd5c8',
    'rail', '#7b6f66',
    'railway', '#7b6f66',
    'ferry', '#5a97c5',
    fallback,
  ];
}

function osmTransportLineWidth(typeField) {
  const token = typeTokenExpression(typeField);
  if (!token) {
    return ['interpolate', ['linear'], ['zoom'], 4, 1.0, 10, 2.5, 14, 4.0];
  }
  const widthAtLow = [
    'match',
    token,
    'motorway', 2.8,
    'trunk', 2.4,
    'primary', 2.0,
    'secondary', 1.6,
    'tertiary', 1.3,
    'residential', 1.0,
    'service', 0.8,
    'rail', 1.2,
    'railway', 1.2,
    1.0,
  ];
  const widthAtHigh = [
    'match',
    token,
    'motorway', 7.0,
    'trunk', 6.0,
    'primary', 5.0,
    'secondary', 4.2,
    'tertiary', 3.6,
    'residential', 2.8,
    'service', 2.0,
    'rail', 2.4,
    'railway', 2.4,
    2.6,
  ];
  return ['interpolate', ['linear'], ['zoom'], 4, widthAtLow, 12, widthAtHigh];
}

function osmLandFillColor(typeField, fallback) {
  const token = typeTokenExpression(typeField);
  if (!token) return fallback;
  return [
    'match',
    token,
    'forest', '#a8c58f',
    'wood', '#9ec086',
    'park', '#b9d79d',
    'grass', '#c9deb1',
    'meadow', '#c8dba2',
    'farmland', '#d6d7a5',
    'residential', '#ece8dd',
    'industrial', '#e2ddd0',
    'commercial', '#e7e2d6',
    'glacier', '#dde8f0',
    'desert', '#e4d1a2',
    'wetland', '#b9d7c3',
    fallback,
  ];
}

function osmWaterFillColor(typeField, fallback) {
  const token = typeTokenExpression(typeField);
  if (!token) return fallback;
  // Prefer substring-based mapping for descriptive classes such as
  // "Estuarine and Marine Wetland" or "Freshwater Emergent Wetland".
  const wetlandClassColor = [
    'case',
    ['>=', ['index-of', 'deepwater', token], 0], '#78addf',
    ['>=', ['index-of', 'riverine', token], 0], '#7fb6e8',
    ['>=', ['index-of', 'estuarine', token], 0], '#71b7c8',
    ['>=', ['index-of', 'marine', token], 0], '#68b0c2',
    ['>=', ['index-of', 'forested', token], 0], '#7aa37d',
    ['>=', ['index-of', 'shrub', token], 0], '#86ad86',
    ['>=', ['index-of', 'emergent', token], 0], '#93b47a',
    ['>=', ['index-of', 'pond', token], 0], '#8fc4e8',
    ['>=', ['index-of', 'lake', token], 0], '#89bee9',
    ['>=', ['index-of', 'wetland', token], 0], '#87bca5',
    fallback,
  ];
  return [
    'coalesce',
    wetlandClassColor,
    [
      'match',
      token,
      'ocean', '#9ec9f5',
      'sea', '#9ec9f5',
      'lake', '#a7d4fb',
      'river', '#8abde8',
      'canal', '#80b5e2',
      'reservoir', '#a0cff2',
      'wetland', '#98c8c3',
      fallback,
    ],
  ];
}

function osmPlacePointColor(typeField, fallback) {
  const token = typeTokenExpression(typeField);
  if (!token) return fallback;
  return [
    'match',
    token,
    'capital', '#513c2f',
    'city', '#6a4f3c',
    'town', '#7a634e',
    'village', '#8f7660',
    fallback,
  ];
}

function osmPlacePointRadius(typeField) {
  const token = typeTokenExpression(typeField);
  if (!token) return ['interpolate', ['linear'], ['zoom'], 4, 2.2, 10, 4.5, 14, 6.0];
  const base = [
    'match',
    token,
    'capital', 5.0,
    'city', 4.2,
    'town', 3.4,
    'village', 2.6,
    2.8,
  ];
  return ['interpolate', ['linear'], ['zoom'], 4, ['*', base, 0.6], 10, base, 14, ['*', base, 1.2]];
}

function classifySemanticKind(layerName, protoInfo) {
  const explicitKind = String(protoInfo?.semantic_kind || '').toLowerCase().trim();
  if (explicitKind && explicitKind !== 'unknown') {
    return explicitKind;
  }

  const text = [
    layerName,
    protoInfo?.name,
    protoInfo?.layer,
    protoInfo?.semantic_category,
    protoInfo?.semantic_type,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  if (/(hydro|water|ocean|sea|lake|river|bay|canal|wetland|marsh)/.test(text)) return 'water';
  if (/(road|rail|transport|route|airport|harbor|port)/.test(text)) return 'transport';
  if (/(boundar|admin|claim|border)/.test(text)) return 'boundary';
  if (/(place|city|town|village|label)/.test(text)) return 'place';
  return 'land';
}

/**
 * Find the best label field from a list of field names.
 * Returns the first field that matches a label pattern, excluding administrative fields.
 * Only considers String-type fields (skips Integer, Real, numeric types).
 */
function findLabelField(fields) {
  if (!fields || fields.length === 0) return null;
  
  // Build a map of field name -> type for type checking
  const fieldInfo = {};
  for (const f of fields) {
    if (typeof f === 'string') {
      fieldInfo[f] = 'unknown'; // Fallback for plain string fields
    } else {
      fieldInfo[f.name] = f.type || 'unknown';
    }
  }
  
  // Numeric types that should not be used as labels
  const numericTypes = ['Integer', 'Real', 'Double', 'Float', 'Long', 'Short', 'Byte'];
  
  // Filter to only String-type fields (excluding numeric/ID types)
  const candidateFields = Object.entries(fieldInfo)
    .filter(([name, type]) => {
      // Exclude administrative patterns
      if (EXCLUDE_FROM_LABELS.some(pattern => pattern.test(name))) {
        return false;
      }
      // Exclude numeric types
      if (numericTypes.some(nt => type?.includes(nt))) {
        return false;
      }
      return true;
    })
    .map(([name]) => name);
  
  // Try each pattern in order of preference
  for (const pattern of LABEL_PATTERNS) {
    const match = candidateFields.find(name => pattern.test(name));
    if (match) return match;
  }
  
  return null;
}

/**
 * Detect temperature or numeric data fields for choropleth visualization.
 * Looks for fields that suggest climate/temperature data, or general numeric metrics.
 */
function detectNumericDataField(fields) {
  if (!fields || fields.length === 0) return null;
  
  const fieldInfo = {};
  for (const f of fields) {
    if (typeof f === 'string') {
      fieldInfo[f] = 'unknown';
    } else {
      fieldInfo[f.name] = f.type || 'unknown';
    }
  }
  
  // Debug: log all fields found
  const numericFields = Object.entries(fieldInfo).filter(([name, type]) => {
    const numericTypes = ['Integer', 'Real', 'Double', 'Float', 'Long'];
    return numericTypes.some(nt => type?.includes(nt));
  });
  console.log('[detectNumericDataField] Available numeric fields:', numericFields.map(([n,t]) => `${n}(${t})`));
  
  // Numeric types that can be visualized
  const numericTypes = ['Integer', 'Real', 'Double', 'Float', 'Long'];
  
  // Look for climate/temperature patterns first (highest priority)
  const climatePatterns = [
    /temp/i,              // temperature
    /precip/i,            // precipitation
    /climate/i,           // climate
    /projection/i,        // projection
    /anomaly/i,           // anomaly
    /rcp/i,               // RCP scenarios
    /scenario/i,          // scenario
  ];
  
  // Find numeric fields matching climate patterns
  for (const [name, type] of Object.entries(fieldInfo)) {
    if (numericTypes.some(nt => type?.includes(nt))) {
      if (climatePatterns.some(p => p.test(name))) {
        return name;
      }
    }
  }
  
  // Second priority: common metric fields (area, density, count, value, etc)
  const metricPatterns = [
    /^acres$/i,           // ACRES (wetlands, land use)
    /^area/i,             // AREA, AreaAcres, etc
    /^value$/i,           // VALUE (general data values)
    /^count$/i,           // COUNT (feature counts)
    /^density/i,          // DENSITY (population, feature density)
    /^population/i,       // POPULATION
    /^elev/i,             // ELEVATION
    /^depth/i,            // DEPTH (bathymetry, water)
    /^height/i,           // HEIGHT (building heights, DEM)
    /^magnitude/i,        // MAGNITUDE (earthquake, seismic)
    /^intensity/i,        // INTENSITY
    /^index$/i,           // INDEX (various indices)
    /^score$/i,           // SCORE
    /^rating$/i,          // RATING
    /^percentage|percent/i, // PERCENTAGE
  ];
  
  // Find numeric fields matching metric patterns
  for (const [name, type] of Object.entries(fieldInfo)) {
    if (numericTypes.some(nt => type?.includes(nt))) {
      if (metricPatterns.some(p => p.test(name))) {
        console.log(`[detectNumericDataField] ✓ Matched metric field: ${name} (type: ${type})`);
        return name;
      }
    }
  }
  
  // Fallback: first numeric field if it has many features (likely gridded data)
  for (const [name, type] of Object.entries(fieldInfo)) {
    if (numericTypes.some(nt => type?.includes(nt))) {
      if (!name.match(/^(id|uuid|fid|pk|shape_|st_)$/i)) {
        console.log(`[detectNumericDataField] ✓ Fallback numeric field: ${name} (type: ${type})`);
        return name;
      }
    }
  }
  
  console.log('[detectNumericDataField] ✗ No suitable numeric field found');
  return null;
}


/**
 * Create a temperature/numeric choropleth color ramp.
 * Uses a perceptually uniform "cool to warm" scale.
 * Automatically adjusts range based on tropical vs temperate regions.
 */
function createTemperatureColorRamp(field, minValue, maxValue) {
  // Auto-detect reasonable range if not provided
  // Tropical regions (like Côte d'Ivoire): use 20-35°C for better differentiation
  // Temperate regions: use 0-30°C
  if (minValue === undefined || maxValue === undefined) {
    minValue = 20;  // More granular for tropical data
    maxValue = 35;
  }
  
  // Edge case: if all values are the same, use a uniform color (middle of scale)
  if (minValue === maxValue || maxValue - minValue < 0.0001) {
    return '#ffffbf'; // Uniform yellow for flat data
  }
  
  // RdYlBu reversed (Red-Yellow-Blue reversed for hot-to-cold)
  // Maps value range to color spectrum with more intermediate stops for better gradation
  return [
    'interpolate',
    ['linear'],
    ['get', field],
    minValue, '#3b4cc0',                                    // Deep blue (cold)
    minValue + (maxValue - minValue) * 0.15, '#5b7ec9',   // Blue
    minValue + (maxValue - minValue) * 0.3, '#89cce3',    // Light blue
    minValue + (maxValue - minValue) * 0.45, '#d9f0f7',   // Very light blue
    minValue + (maxValue - minValue) * 0.5, '#ffffbf',    // Yellow (neutral/middle)
    minValue + (maxValue - minValue) * 0.55, '#fce6a0',   // Light orange
    minValue + (maxValue - minValue) * 0.7, '#f89654',    // Orange
    minValue + (maxValue - minValue) * 0.85, '#e85d3f',   // Dark orange
    maxValue, '#b30000'                                     // Dark red (hot)
  ];
}

/**
 * Create a precipitation color ramp (sequential light-to-dark blue).
 */
function createPrecipitationColorRamp(field, minValue = 0, maxValue = 100) {
  // Edge case: if all values are the same, use a uniform color
  if (minValue === maxValue || maxValue - minValue < 0.0001) {
    return '#6baed6'; // Uniform medium blue for flat data
  }
  
  // Sequential scale: light (dry) → dark blue (wet)
  return [
    'interpolate',
    ['linear'],
    ['get', field],
    minValue, '#f7fbff',                                    // Very light blue (dry)
    minValue + (maxValue - minValue) * 0.15, '#deebf7',   // Light blue
    minValue + (maxValue - minValue) * 0.3, '#c6dbef',    // Light-medium blue
    minValue + (maxValue - minValue) * 0.45, '#9ecae1',   // Medium blue
    minValue + (maxValue - minValue) * 0.5, '#6baed6',    // Medium-dark blue
    minValue + (maxValue - minValue) * 0.7, '#3182bd',    // Dark blue
    minValue + (maxValue - minValue) * 0.85, '#08519c',   // Very dark blue
    maxValue, '#08306b'                                     // Navy blue (very wet)
  ];
}

/**
 * Create a precipitation/anomaly color ramp (diverging blue-white-red).
 */
function createAnomalyColorRamp(field, minValue = -3, maxValue = 3) {
  // Edge case: if all values are the same, use a uniform color
  if (minValue === maxValue || maxValue - minValue < 0.0001) {
    return '#ffffbf'; // Uniform white/yellow for flat data (neutral)
  }
  
  return [
    'interpolate',
    ['linear'],
    ['get', field],
    minValue, '#313695',           // Dark blue (negative)
    minValue + (maxValue - minValue) * 0.25, '#4575b4',  // Blue
    minValue + (maxValue - minValue) * 0.45, '#abd9e9',  // Light blue
    minValue + (maxValue - minValue) * 0.5, '#ffffbf',   // White (zero)
    minValue + (maxValue - minValue) * 0.55, '#fdae61',  // Light orange
    minValue + (maxValue - minValue) * 0.75, '#f46d43',  // Orange
    maxValue, '#a50026'            // Dark red (positive)
  ];
}

/**
 * Create a generic metric color ramp (sequential yellow-orange-red for area/count/density).
 * Good for positive-only metrics like ACRES, POPULATION, ELEVATION, etc.
 * Handles edge case where minValue === maxValue by using a uniform color.
 */
function createMetricColorRamp(field, minValue = 0, maxValue = 100) {
  // Edge case: if all values are the same, use a uniform color (middle of scale)
  if (minValue === maxValue || maxValue - minValue < 0.0001) {
    return '#e8843f'; // Uniform medium orange for flat data
  }
  
  // Sequential scale: warm orange (low) → dark red (high) - no yellow
  return [
    'interpolate',
    ['linear'],
    ['get', field],
    minValue, '#ff9800',                                    // Orange (low)
    minValue + (maxValue - minValue) * 0.15, '#ffd699',   // Light peach-orange
    minValue + (maxValue - minValue) * 0.3, '#ffc27d',    // Peachy orange
    minValue + (maxValue - minValue) * 0.45, '#ffb347',   // Orange
    minValue + (maxValue - minValue) * 0.6, '#e8843f',    // Medium orange
    minValue + (maxValue - minValue) * 0.75, '#d35400',   // Dark orange
    minValue + (maxValue - minValue) * 0.9, '#c0392b',    // Red-orange
    maxValue, '#922b21'                                     // Dark red (high)
  ];
}

/**
 * Check if a field represents temperature-like data.
 */
function isTemperatureField(fieldName) {
  return /temp/i.test(fieldName);
}

/**
 * Check if a field represents anomaly or diverging data.
 */
function isAnomalyField(fieldName) {
  return /anomaly|difference|change|delta/i.test(fieldName);
}

/**
 * Build a dynamic style for arbitrary vector tile data.
 * @param {string} pmtilesUrl - PMTiles URL (with or without pmtiles:// protocol)
 * @param {Array<{id: string, geometry_type?: string}>} vectorLayers - Vector layer info from PMTiles metadata
 * @param {object} options - Build options
 * @param {boolean} options.isMlt - Whether the source uses MLT encoding (default: true)
 * @param {Array<{name: string, geometry_type: string}>} options.protocolLayers - Layer info from protocol JSON
 * @returns {object} - MapLibre style specification
 */
export function buildDynamicStyle(pmtilesUrl, vectorLayers, options = {}) {
  const { isMlt = true, protocolLayers = [], tilesUrl = null, minLabelZoom = 6 } = options;

  // The four study datasets are colored like their paper figures (figureStyles.js); every other dataset keeps the generic style below.
  const figure = figureStyleLayers(figureStyleKey(options.datasetId));

  // Build lookup from protocol layers for geometry type info
  const protoLayerByName = Object.fromEntries(
    protocolLayers.map((l) => [l.name, l])
  );

  // Build source — either HTTP tile template (MBTiles server) or PMTiles archive
  let source;
  // Declared out here because the fallback below needs it too: as a const inside
  // the else branch it was out of scope there, so the one path that handles a
  // source with no layers raised ReferenceError instead of building a style.
  let sourceUrl = null;
  if (tilesUrl) {
    source = { type: 'vector', tiles: [tilesUrl] };
  } else {
    sourceUrl = pmtilesUrl.startsWith('pmtiles://') ? pmtilesUrl : `pmtiles://${pmtilesUrl}`;
    source = { type: 'vector', url: sourceUrl };
  }
  if (isMlt) {
    source.encoding = 'mlt';
  }

  // Use vectorLayers from PMTiles metadata, or fall back to protocolLayers
  // PMTiles metadata might be empty for some sources
  let layersToProcess = vectorLayers || [];
  if (layersToProcess.length === 0 && protocolLayers.length > 0) {
    // Use protocol layers as fallback, adapting format
    layersToProcess = protocolLayers.map(l => ({
      id: l.name,
      name: l.name,
      geometry_type: l.geometry_type,
    }));
  }

  // If still no layers, create a generic catch-all.
  //
  // Reported as an error, not a warning. A catch-all draws whatever geometry it
  // finds with none of the dataset's layer structure, so a benchmark run against
  // one measures something that is not the dataset -- the same failure the
  // Python side had when generate_vector_profile answered an empty layer list
  // with one attribute-less catch-all layer, which is what withdrew the
  // 2026-08-29 Amsterdam figures. console_error_count is defined as the errors
  // the browser reported during visualization, and a warning is not one, so at
  // console.warn this was invisible to the metric group whose whole purpose is
  // to catch it.
  if (layersToProcess.length === 0 && !figure) {
    console.error(
      'No vector layers found in PMTiles metadata or protocol; falling back to a '
      + 'catch-all style. Figures measured against it are not measurements of '
      + 'this dataset.',
    );
    return buildCatchAllStyle(sourceUrl || pmtilesUrl, isMlt);
  }

  // Categorize layers by geometry type
  const fillLayers = [];
  const lineLayers = [];
  const pointLayers = [];
  const labelLayers = [];

  let fillIdx = 0, lineIdx = 0, pointIdx = 0;

  for (const vl of layersToProcess) {
    const layerName = vl.id || vl.name;
    const protoInfo = protoLayerByName[layerName];
    const geomType = (protoInfo?.geometry_type || vl.geometry_type || '').toLowerCase();
    const kind = classifySemanticKind(layerName, protoInfo);
    const typeField = resolveTypeField(protoInfo);

    if (geomType.includes('polygon') || geomType.includes('multipolygon')) {
      const isWaterLayer = kind === 'water';
      const dataField = !isWaterLayer ? detectNumericDataField(protoInfo?.fields) : null;

      // Water/wetland: vivid saturated fill on dark background.
      // Non-water reference layers (e.g. state boundary): nearly transparent so
      // features rendered on top (wetlands, etc.) read clearly against the dark bg.
      let fillColor, fillOpacity;
      if (isWaterLayer) {
        fillColor = osmWaterFillColor(typeField, '#9ecbf3');
        fillOpacity = 0.82;
      } else if (kind === 'land' || kind === 'terrain' || kind === 'building' || kind === 'infrastructure') {
        fillColor = osmLandFillColor(typeField, '#d7d6c7');
        fillOpacity = 0.78;
      } else if (kind === 'boundary') {
        fillColor = '#e6e1d2';
        fillOpacity = 0.38;
      } else {
        fillColor = '#d9d3c5';
        fillOpacity = 0.65;
      }

      fillLayers.push({
        id: `${layerName}-fill`,
        type: 'fill',
        source: 'dataset',
        'source-layer': layerName,
        paint: {
          'fill-color': fillColor,
          'fill-opacity': fillOpacity,
        },
      });

      const outlineColor = isWaterLayer ? 'rgba(70, 126, 180, 0.82)' : 'rgba(124, 117, 99, 0.76)';
      const outlineWidth = kind === 'boundary' ? 1.4 : 1;
      
      fillLayers.push({
        id: `${layerName}-outline`,
        type: 'line',
        source: 'dataset',
        'source-layer': layerName,
        paint: {
          'line-color': outlineColor,
          'line-width': outlineWidth,
          'line-opacity': 0.9,
        },
      });

      // Add label layer for polygons (or data values for choropleth)
      const labelLayer = createLabelLayer(layerName, 'polygon', protoInfo?.fields, dataField, minLabelZoom);
      if (labelLayer) labelLayers.push(labelLayer);

    } else if (geomType.includes('line') || geomType.includes('multiline')) {
      const baseLineColor = kind === 'water'
        ? '#5a9fce'
        : kind === 'transport'
          ? '#d8cbb7'
          : kind === 'boundary'
            ? '#8a8174'
            : LINE_COLORS[lineIdx % LINE_COLORS.length];
      lineIdx++;

      const lineColor = kind === 'transport'
        ? osmTransportLineColor(typeField, baseLineColor)
        : baseLineColor;
      const lineWidth = kind === 'transport'
        ? osmTransportLineWidth(typeField)
        : ['interpolate', ['linear'], ['zoom'], 4, 0.8, 10, 2.2, 14, 3.2];

      lineLayers.push({
        id: `${layerName}-line`,
        type: 'line',
        source: 'dataset',
        'source-layer': layerName,
        paint: {
          'line-color': lineColor,
          'line-width': lineWidth,
          'line-opacity': kind === 'boundary' ? 0.75 : 0.95,
          'line-dasharray': kind === 'boundary' ? [3, 2] : [1, 0],
        },
      });

      // Add label layer for lines
      const lineLabelLayer = createLabelLayer(layerName, 'line', protoInfo?.fields, null, minLabelZoom + 1);
      if (lineLabelLayer) labelLayers.push(lineLabelLayer);

    } else if (geomType.includes('point') || geomType.includes('multipoint')) {
      const color = kind === 'place'
        ? osmPlacePointColor(typeField, '#70574b')
        : POINT_COLORS[pointIdx % POINT_COLORS.length];
      const radius = kind === 'place'
        ? osmPlacePointRadius(typeField)
        : 5;
      pointIdx++;

      pointLayers.push({
        id: `${layerName}-point`,
        type: 'circle',
        source: 'dataset',
        'source-layer': layerName,
        paint: {
          'circle-color': color,
          'circle-radius': radius,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1,
          'circle-opacity': 0.95,
        },
      });

      // Add label layer for points
      const pointLabelLayer = createLabelLayer(layerName, 'point', protoInfo?.fields, null, minLabelZoom);
      if (pointLabelLayer) labelLayers.push(pointLabelLayer);

    } else {
      // Unknown geometry — add all types with $type filters
      const fillColor = FILL_COLORS[fillIdx % FILL_COLORS.length];
      const lineColor = LINE_COLORS[lineIdx % LINE_COLORS.length];
      const pointColor = POINT_COLORS[pointIdx % POINT_COLORS.length];
      fillIdx++; lineIdx++; pointIdx++;

      fillLayers.push({
        id: `${layerName}-fill`,
        type: 'fill',
        source: 'dataset',
        'source-layer': layerName,
        filter: ['==', '$type', 'Polygon'],
        paint: { 'fill-color': fillColor, 'fill-opacity': 0.4 },
      });
      fillLayers.push({
        id: `${layerName}-outline`,
        type: 'line',
        source: 'dataset',
        'source-layer': layerName,
        filter: ['==', '$type', 'Polygon'],
        paint: { 'line-color': fillColor, 'line-width': 1, 'line-opacity': 0.8 },
      });
      lineLayers.push({
        id: `${layerName}-line`,
        type: 'line',
        source: 'dataset',
        'source-layer': layerName,
        filter: ['==', '$type', 'LineString'],
        paint: { 'line-color': lineColor, 'line-width': 2 },
      });
      pointLayers.push({
        id: `${layerName}-point`,
        type: 'circle',
        source: 'dataset',
        'source-layer': layerName,
        filter: ['==', '$type', 'Point'],
        paint: { 'circle-color': pointColor, 'circle-radius': 5, 'circle-stroke-color': '#fff', 'circle-stroke-width': 1 },
      });

      // Add label layer for unknown geometry
      const unknownLabelLayer = createLabelLayer(layerName, 'unknown', protoInfo?.fields, null, minLabelZoom);
      if (unknownLabelLayer) labelLayers.push(unknownLabelLayer);
    }
  }

  // Build final layers array: background → fills → lines → points → labels.
  // A figure dataset replaces the first four with the figure's own ordered layers; its label layers are kept.
  const layers = figure
    ? [
      { id: 'background', type: 'background', paint: { 'background-color': figure.background } },
      ...figure.layers,
      ...labelLayers,
    ]
    : [
      { id: 'background', type: 'background', paint: { 'background-color': '#eef2e6' } },
      ...fillLayers,
      ...lineLayers,
      ...pointLayers,
      ...labelLayers,
    ];

  return {
    version: 8,
    sources: { dataset: source },
    layers,
  };
}

/**
 * Create a symbol layer for labels.
 * Uses actual field names from protocol when available, otherwise tries common patterns.
 * For choropleth data, can display data values instead.
 */
function createLabelLayer(layerName, geomHint, fields, dataField, minLabelZoom = 6) {
  // If we have choropleth data, show data values instead of text labels
  if (dataField) {
    const layer = {
      id: `${layerName}-data`,
      type: 'symbol',
      source: 'dataset',
      'source-layer': layerName,
      minzoom: Math.max(4, minLabelZoom),
      layout: {
        'text-field': ['format',
          ['number-format', ['get', dataField], {}],
          { 'font-scale': 0.8 }
        ],
        'text-font': ['Roboto Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 8, 9, 14, 12],
        'text-anchor': 'center',
        'text-allow-overlap': false,
        'text-ignore-placement': true,
        'text-optional': true,
      },
      paint: {
        'text-color': '#ffffff',
        'text-halo-color': 'rgba(0, 0, 0, 0.7)',
        'text-halo-width': 1,
        'text-halo-blur': 0.5,
      },
    };
    console.log(`[dynamicStyle] Layer "${layerName}": displaying data values from field "${dataField}"`);
    return layer;
  }
  
  // Find the best label field from available fields
  const labelField = findLabelField(fields);
  
  // Debug: log detected label field
  console.log(`[dynamicStyle] Layer "${layerName}": label field = "${labelField || 'none'}" (from ${fields?.length || 0} fields)`);
  
  // If no label field found, skip creating label layer
  if (!labelField) {
    // Fallback for sparse protocol metadata: try common label/type keys directly.
    const fallbackExpr = ['coalesce',
      ['get', 'name'],
      ['get', 'NAME'],
      ['get', 'name_en'],
      ['get', 'NAME_EN'],
      ['get', 'name_long'],
      ['get', 'NAME_LONG'],
      ['get', 'featurecla'],
      ['get', 'FEATURECLA'],
      ['get', 'type'],
      ['get', 'TYPE'],
    ];

    console.log(`[dynamicStyle] Layer "${layerName}": using fallback label expression`);

    const fallbackLayer = {
      id: `${layerName}-label`,
      type: 'symbol',
      source: 'dataset',
      'source-layer': layerName,
      minzoom: Math.max(4, minLabelZoom),
      filter: ['all',
        ['!=', fallbackExpr, null],
        ['!=', fallbackExpr, ''],
        ['!=', fallbackExpr, 'N/A'],
        ['!=', fallbackExpr, 'n/a'],
        ['!=', fallbackExpr, 'None'],
        ['!=', fallbackExpr, 'none'],
        ['!=', fallbackExpr, 'null'],
      ],
      layout: {
        'text-field': fallbackExpr,
        'text-font': ['Roboto Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 8, 9, 14, 13],
        'text-anchor': 'center',
        'text-max-width': 10,
        'text-allow-overlap': false,
        'text-ignore-placement': false,
        'text-optional': true,
        'symbol-spacing': 500,
      },
      paint: {
        'text-color': '#ffffff',
        'text-halo-color': 'rgba(0, 0, 0, 0.8)',
        'text-halo-width': 1.5,
        'text-halo-blur': 0.5,
      },
    };

    if (geomHint === 'line') {
      fallbackLayer.layout['symbol-placement'] = 'line';
      fallbackLayer.layout['text-anchor'] = 'center';
      fallbackLayer.layout['text-rotation-alignment'] = 'map';
      fallbackLayer.layout['text-pitch-alignment'] = 'viewport';
    } else if (geomHint === 'polygon') {
      fallbackLayer.layout['symbol-placement'] = 'point';
    } else if (geomHint === 'point') {
      fallbackLayer.layout['text-offset'] = [0, 1.2];
      fallbackLayer.layout['text-anchor'] = 'top';
    }

    return fallbackLayer;
  }
  
  // Build text-field expression with filter for non-empty values
  const textFieldExpr = ['get', labelField];

  // Placeholder values used in scientific/GIS datasets that should not be shown as labels
  const EMPTY_PLACEHOLDERS = ['', 'N/A', 'n/a', 'NA', '-', 'None', 'none', 'null', '0', 'Unknown', 'unknown'];

  const layer = {
    id: `${layerName}-label`,
    type: 'symbol',
    source: 'dataset',
    'source-layer': layerName,
    minzoom: Math.max(4, minLabelZoom),
    filter: ['all',
      ['has', labelField],
      ['!=', ['get', labelField], null],
      ...EMPTY_PLACEHOLDERS.map(v => ['!=', ['get', labelField], v]),
    ],
    layout: {
      'text-field': textFieldExpr,
      'text-font': ['Roboto Regular'],
      'text-size': ['interpolate', ['linear'], ['zoom'], Math.max(4, minLabelZoom), 10, 14, 14],
      'text-anchor': 'center',
      'text-max-width': 10,
      'text-allow-overlap': false,
      'text-ignore-placement': false,
      'text-optional': true,  // Allow label to be hidden if it collides
      'symbol-spacing': 500,  // Min distance between repeated labels on a line
    },
    paint: {
      'text-color': '#ffffff',
      'text-halo-color': 'rgba(0, 0, 0, 0.8)',
      'text-halo-width': 1.5,
      'text-halo-blur': 0.5,
    },
  };

  // Adjust placement based on geometry hint
  if (geomHint === 'line') {
    layer.layout['symbol-placement'] = 'line';
    layer.layout['text-anchor'] = 'center';
    layer.layout['text-rotation-alignment'] = 'map';
    layer.layout['text-pitch-alignment'] = 'viewport';
  } else if (geomHint === 'polygon') {
    // For polygons, place label at center
    layer.layout['symbol-placement'] = 'point';
  } else if (geomHint === 'point') {
    layer.layout['text-offset'] = [0, 1.2];
    layer.layout['text-anchor'] = 'top';
  }

  return layer;
}

/**
 * Build a catch-all style when no layer info is available.
 * This happens when PMTiles metadata is empty and protocol has no layers.
 * Uses wildcard source-layer matching via empty string (renders all layers).
 */
function buildCatchAllStyle(sourceUrl, isMlt) {
  const source = { type: 'vector', url: sourceUrl };
  if (isMlt) {
    source.encoding = 'mlt';
  }

  // Note: MapLibre doesn't support wildcard source-layer, so we create
  // layers without source-layer filter to catch any geometry
  const layers = [
    { id: 'background', type: 'background', paint: { 'background-color': '#1a1a2e' } },
    {
      id: 'catchall-fill',
      type: 'fill',
      source: 'dataset',
      filter: ['==', '$type', 'Polygon'],
      paint: { 'fill-color': '#4f8ff7', 'fill-opacity': 0.4 },
    },
    {
      id: 'catchall-outline',
      type: 'line',
      source: 'dataset',
      filter: ['==', '$type', 'Polygon'],
      paint: { 'line-color': '#4f8ff7', 'line-width': 1 },
    },
    {
      id: 'catchall-line',
      type: 'line',
      source: 'dataset',
      filter: ['==', '$type', 'LineString'],
      paint: { 'line-color': '#3dd68c', 'line-width': 2 },
    },
    {
      id: 'catchall-point',
      type: 'circle',
      source: 'dataset',
      filter: ['==', '$type', 'Point'],
      paint: { 'circle-color': '#f5a623', 'circle-radius': 5, 'circle-stroke-color': '#fff', 'circle-stroke-width': 1 },
    },
  ];

  return {
    version: 8,
    sources: { dataset: source },
    layers,
  };
}
