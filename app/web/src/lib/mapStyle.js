/**
 * OSM Liberty style builder for OpenMapTiles schema.
 * Adapts the base OSM Liberty style for PMTiles + MLT rendering with WOFF2 fonts.
 * Based on maps-stack pattern.
 */

const STYLE_ASSET = '/map-styles/osm-liberty/style.json';
let baseStyleCache = null;

/**
 * Load the base OSM Liberty style (cached).
 * @returns {Promise<object>} - MapLibre style specification
 */
async function loadBaseStyle() {
  if (!baseStyleCache) {
    const response = await fetch(STYLE_ASSET);
    if (!response.ok) {
      throw new Error(`Failed to load base style: ${response.status}`);
    }
    baseStyleCache = await response.json();
  }
  return baseStyleCache;
}

// Locale-specific name field priority
const NAME_FIELDS = {
  en: ['name:latin', 'name:en', 'name_en', 'name', 'name:ru', 'name_ru'],
  ru: ['name:ru', 'name_ru', 'name', 'name:latin', 'name:en', 'name_en'],
  he: ['name:he', 'name', 'name:en', 'name:latin', 'name_en'],
  ar: ['name:ar', 'name', 'name:en', 'name:latin', 'name_en'],
};

/**
 * Build a MapLibre style for OSM Liberty with PMTiles source.
 * @param {string} pmtilesUrl - PMTiles URL (with or without pmtiles:// protocol)
 * @param {object} options - Build options
 * @param {string} options.locale - Locale for label expressions ('en', 'ru', 'he', 'ar')
 * @param {boolean} options.isMlt - Whether the source uses MLT encoding (default: true)
 * @returns {Promise<object>} - MapLibre style specification
 */
export async function buildMapStyle(pmtilesUrl, options = {}) {
  const { locale = 'en', isMlt = true, tilesUrl = null } = options;

  // Deep clone the base style to avoid mutation
  const style = JSON.parse(JSON.stringify(await loadBaseStyle()));

  // 1. Set source — either HTTP tile template (MBTiles server) or PMTiles archive
  const src = style.sources.openmaptiles;
  if (tilesUrl) {
    src.tiles = [tilesUrl];
    delete src.url;
  } else {
    src.url = pmtilesUrl.startsWith('pmtiles://') ? pmtilesUrl : `pmtiles://${pmtilesUrl}`;
  }
  if (isMlt) {
    src.encoding = 'mlt';
  }

  // 2. Make sprite URL absolute (MapLibre rejects origin-relative paths)
  if (style.sprite && style.sprite.startsWith('/')) {
    style.sprite = window.location.origin + style.sprite;
  }

  // 3. Remove glyphs key — fonts are provided via CSS @font-face
  delete style.glyphs;

  // 4. Add font-faces block for MapLibre Native compatibility (future-proofing)
  style['font-faces'] = {
    'Roboto Regular': [
      { url: '/fonts/roboto-cyrillic-400-normal.woff2', 'unicode-range': ['U+0301', 'U+0400-045F', 'U+0490-0491', 'U+04B0-04B1', 'U+2116'] },
      { url: '/fonts/roboto-latin-400-normal.woff2', 'unicode-range': ['U+0000-00FF', 'U+0100-024F'] },
      { url: '/fonts/noto-sans-hebrew-400-normal.woff2', 'unicode-range': ['U+0590-05FF', 'U+200C-2010', 'U+20AA', 'U+25CC', 'U+FB1D-FB4F'] },
      { url: '/fonts/noto-sans-arabic-400-normal.woff2', 'unicode-range': ['U+0600-06FF', 'U+0750-077F', 'U+08A0-08FF', 'U+FB50-FDFF', 'U+FE70-FEFF'] },
    ],
    'Roboto Medium': [
      { url: '/fonts/roboto-cyrillic-500-normal.woff2', 'unicode-range': ['U+0301', 'U+0400-045F', 'U+0490-0491', 'U+04B0-04B1', 'U+2116'] },
      { url: '/fonts/roboto-latin-500-normal.woff2', 'unicode-range': ['U+0000-00FF', 'U+0100-024F'] },
      { url: '/fonts/noto-sans-hebrew-500-normal.woff2', 'unicode-range': ['U+0590-05FF', 'U+200C-2010', 'U+20AA', 'U+25CC', 'U+FB1D-FB4F'] },
      { url: '/fonts/noto-sans-arabic-500-normal.woff2', 'unicode-range': ['U+0600-06FF', 'U+0750-077F', 'U+08A0-08FF', 'U+FB50-FDFF', 'U+FE70-FEFF'] },
    ],
    'Roboto Condensed Italic': [
      { url: '/fonts/roboto-condensed-cyrillic-400-italic.woff2', 'unicode-range': ['U+0301', 'U+0400-045F', 'U+0490-0491', 'U+04B0-04B1', 'U+2116'] },
      { url: '/fonts/roboto-condensed-latin-400-italic.woff2', 'unicode-range': ['U+0000-00FF', 'U+0100-024F'] },
    ],
  };

  // 5. Remove external raster relief layer (avoids CDN dependency)
  delete style.sources.natural_earth_shaded_relief;
  style.layers = style.layers.filter(
    (l) => l.source !== 'natural_earth_shaded_relief' && l.id !== 'natural_earth'
  );

  // 6. Apply locale-aware label expressions
  const fields = NAME_FIELDS[locale] || NAME_FIELDS.en;
  for (const layer of style.layers) {
    if (layer.type !== 'symbol' || !layer.layout) continue;
    
    const tf = layer.layout['text-field'];
    // Match simple field references like {name} or {name_en}
    const match = typeof tf === 'string' && tf.match(/^\{([^}]+)\}$/);
    if (match && (match[1] === 'name' || match[1] === 'name_en' || match[1] === 'name:latin')) {
      layer.layout['text-field'] = ['coalesce', ...fields.map((f) => ['get', f])];
    }
  }

  return style;
}

/**
 * Create an empty fallback style (gray background).
 * Used when no PMTiles file is available yet.
 * @returns {object} - MapLibre style specification
 */
export function emptyMapStyle() {
  return {
    version: 8,
    sources: {},
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': '#1a1a2e' } },
    ],
  };
}
