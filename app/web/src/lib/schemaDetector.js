/**
 * Schema detection for vector tile layers.
 * Detects whether the tile data uses OpenMapTiles schema (from Planetiler OSM processing)
 * or an unknown/custom schema.
 */

// OpenMapTiles schema layer names (from Planetiler OSM processing)
const OPENMAPTILES_LAYERS = new Set([
  'aerodrome_label',
  'aeroway',
  'boundary',
  'building',
  'housenumber',
  'landcover',
  'landuse',
  'mountain_peak',
  'park',
  'place',
  'poi',
  'transportation',
  'transportation_name',
  'water',
  'water_name',
  'waterway',
]);

// Minimum number of matching layers to consider it OpenMapTiles schema
const MIN_MATCH_THRESHOLD = 3;

/**
 * Detect if the vector layers follow the OpenMapTiles schema.
 * @param {Array<{id: string}>} vectorLayers - Array of vector layer info from PMTiles metadata
 * @returns {'openmaptiles' | 'unknown'} - Detected schema type
 */
export function detectSchema(vectorLayers) {
  if (!vectorLayers || vectorLayers.length === 0) {
    return 'unknown';
  }

  const layerNames = new Set(vectorLayers.map(l => l.id || l.name));
  let matchCount = 0;

  for (const name of layerNames) {
    if (OPENMAPTILES_LAYERS.has(name)) {
      matchCount++;
    }
  }

  return matchCount >= MIN_MATCH_THRESHOLD ? 'openmaptiles' : 'unknown';
}

/**
 * Detect locale from dataset name or metadata.
 * Returns locale code for label expressions.
 * @param {string} datasetName - Dataset name (e.g., 'israel-and-palestine-latest')
 * @returns {'he' | 'ar' | 'ru' | 'en'} - Detected locale
 */
export function detectLocale(datasetName) {
  const name = (datasetName || '').toLowerCase();
  
  // Hebrew-speaking regions
  if (name.includes('israel') || name.includes('palestine')) {
    return 'he';
  }
  
  // Arabic-speaking regions
  if (
    name.includes('egypt') || name.includes('jordan') || name.includes('lebanon') ||
    name.includes('syria') || name.includes('iraq') || name.includes('saudi') ||
    name.includes('uae') || name.includes('emirates') || name.includes('qatar') ||
    name.includes('bahrain') || name.includes('kuwait') || name.includes('oman') ||
    name.includes('yemen') || name.includes('libya') || name.includes('tunisia') ||
    name.includes('algeria') || name.includes('morocco')
  ) {
    return 'ar';
  }
  
  // Russian-speaking regions
  if (
    name.includes('russia') || name.includes('belarus') || name.includes('ukraine') ||
    name.includes('kazakhstan') || name.includes('uzbekistan') || name.includes('tajikistan') ||
    name.includes('kyrgyzstan') || name.includes('turkmenistan')
  ) {
    return 'ru';
  }
  
  // Default to English
  return 'en';
}
