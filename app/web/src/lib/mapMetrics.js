import maplibregl from 'maplibre-gl';
import {
  countTileTraffic, resetTileTraffic, sumTileTrafficBytes,
  tileTrafficMark, tileTrafficSince,
} from './tileTraffic';

const PHASE_TIMEOUT_MS = 30_000;

// The benchmark viewport. Fixed rather than inherited from the window so runs
// are reproducible across machines and window sizes; 2560x1600 matches the
// display the study reports.
export const VIEWPORT_WIDTH = 2560;
export const VIEWPORT_HEIGHT = 1600;

// Reported as-is rather than averaged: these describe the machine, not the run.
const PROVENANCE_KEYS = [
  'gpu_renderer', 'device_pixel_ratio', 'viewport_width', 'viewport_height',
];
// Worst observed value is reported, so an intermittent failure is not averaged away.
const WORST_CASE_KEYS = ['missing_tile_count', 'console_error_count'];

/**
 * The mean of the measurements that succeeded, rounded to whole milliseconds.
 *
 * Used where the paper defines a metric per operation but the benchmark
 * performs the operation more than once — the two pans, the two visibility
 * changes. A phase that timed out contributes null rather than a zero, and a
 * set with nothing in it is null rather than 0, so a stall stays visible.
 */
export function mean(values) {
  const measured = values.filter((v) => typeof v === 'number');
  if (measured.length === 0) return null;
  return Math.round(measured.reduce((a, b) => a + b, 0) / measured.length);
}

function median(values) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[mid]
    : Math.round((sorted[mid - 1] + sorted[mid]) / 2);
}

// A message longer than this is a stack dump rather than a message.
const MAX_CONSOLE_ERROR_CHARS = 300;
// A render loop that errors every frame would otherwise put thousands of
// identical strings on the protocol.
export const MAX_DISTINCT_CONSOLE_ERRORS = 20;

function formatErrorArg(arg) {
  if (arg instanceof Error) return `${arg.name}: ${arg.message}`;
  if (typeof arg === 'string') return arg;
  try { return String(arg); } catch (_) { return '[unprintable]'; }
}

function formatErrorArgs(args) {
  const text = args.map(formatErrorArg).join(' ').trim();
  return text.length > MAX_CONSOLE_ERROR_CHARS
    ? `${text.slice(0, MAX_CONSOLE_ERROR_CHARS)}…`
    : text;
}

/**
 * Counts errors and keeps what they said.
 *
 * console_error_count is one of the paper's eighteen metrics and it recorded a
 * number and never the text, so a run reporting four errors could not be
 * explained afterwards without reproducing it. Playwright's `pageerror`
 * listener is not a substitute: it catches uncaught exceptions, not
 * `console.error` calls, and attaching a Playwright console listener instead
 * would enable Runtime.consoleAPICalled over CDP for every message the page
 * logs — overhead landing on the timings this benchmark exists to measure.
 * Recording in the page costs nothing that is not already being paid.
 *
 * Distinct messages with a count each, rather than a transcript: smaller, and
 * it answers "what went wrong" instead of "how many times".
 */
export function errorLog(limit = MAX_DISTINCT_CONSOLE_ERRORS) {
  const counts = new Map();
  let total = 0;
  let untracked = 0;

  return {
    record(...args) {
      total += 1;
      const message = formatErrorArgs(args);
      if (counts.has(message)) counts.set(message, counts.get(message) + 1);
      else if (counts.size < limit) counts.set(message, 1);
      else untracked += 1;
    },
    get count() { return total; },
    messages() {
      const out = [...counts].map(([message, count]) => ({ message, count }));
      if (untracked) {
        out.push({
          message: `[truncated] ${untracked} further error(s) of other kinds were not recorded`,
          count: untracked,
        });
      }
      return out;
    },
  };
}

/**
 * The messages seen across repeated runs of one format.
 *
 * console_error_count is reported as the worst run rather than the typical one,
 * so a message is reported at its worst occurrence too. Left to the numeric
 * path in aggregateRuns these came out null, an array not being a number.
 */
export function mergeConsoleErrors(runs) {
  const worst = new Map();
  for (const run of runs) {
    for (const entry of run.console_errors ?? []) {
      worst.set(entry.message, Math.max(worst.get(entry.message) ?? 0, entry.count));
    }
  }
  return [...worst].map(([message, count]) => ({ message, count }));
}

/**
 * Combine repeated measurements of one format into a single reported result.
 *
 * A single run of a browser benchmark is noise, so each format is measured
 * several times. Timings and byte totals are reported as medians with the
 * observed spread; runs whose phase timed out (null) are excluded rather than
 * counted as zero.
 */
export function aggregateRuns(runs) {
  if (!runs || runs.length === 0) return null;

  const out = { runs: runs.length, spread: {} };

  for (const key of Object.keys(runs[0])) {
    if (PROVENANCE_KEYS.includes(key)) {
      out[key] = runs[0][key];
      continue;
    }
    if (key === 'render_success') {
      out[key] = runs.every((r) => r[key] === true);
      continue;
    }
    if (key === 'console_errors') {
      out[key] = mergeConsoleErrors(runs);
      continue;
    }
    const values = runs.map((r) => r[key]).filter((v) => typeof v === 'number');
    if (values.length === 0) {
      out[key] = null;
      continue;
    }
    if (WORST_CASE_KEYS.includes(key)) {
      out[key] = Math.max(...values);
      continue;
    }
    out[key] = median(values);
    out.spread[key] = { min: Math.min(...values), max: Math.max(...values) };
  }

  return out;
}

/**
 * Run the standardized benchmark against one tile archive and return the
 * metrics named in the paper's evaluation framework.
 *
 * The map is created here rather than passed in, because the initial-render
 * metrics are defined as elapsed time from *initiating map loading*. Creating
 * it outside would leave tiles already in flight before the clock started.
 *
 * Sequence: cold render at z10 -> pan one viewport horizontally, then one
 * viewport vertically -> zoom to 14 -> disable and re-enable a layer.
 *
 * A phase that never settles resolves as null rather than as the timeout
 * duration, so a stalled run is distinguishable from a slow one.
 */
export async function collectMapMetrics({ container, style, center }) {
  resetTileTraffic();

  const errors = installErrorCounters();
  // Distinct tiles that failed, not error events: MapLibre re-fires on retry,
  // and the metric counts tiles.
  const failedTiles = new Set();
  let unidentifiedTileFailures = 0;
  let phaseMark = 0;

  /** Tiles delivered since the previous call. */
  const sliceSinceLast = () => {
    const slice = tileTrafficSince(phaseMark);
    phaseMark = tileTrafficMark();
    return slice;
  };

  const t0 = performance.now();
  const map = new maplibregl.Map({
    container,
    style,
    center,
    zoom: 10,
    renderWorldCopies: false,
    fadeDuration: 0,
    attributionControl: false,
  });
  map.on('error', (e) => {
    if (!e) return;
    // missing_tile_count is "tiles that failed to load or render". Only an
    // event carrying a tile is one; a source-level failure — a TileJSON that
    // would not fetch — is an error but not a missing tile, and counting it as
    // one inflated the metric.
    if (!e.tile) {
      errors.mapErrors += 1;
      return;
    }
    const canonical = e.tile.tileID?.canonical;
    if (canonical) {
      failedTiles.add(`${e.sourceId ?? ''}/${canonical.z}/${canonical.x}/${canonical.y}`);
    } else {
      unidentifiedTileFailures += 1;
    }
  });

  try {
    // --- Cold initial render -------------------------------------------------
    // "Sufficient visual content for meaningful user interaction" is a painted
    // frame, not an arrived byte. Tile content reaching the source is the input
    // to that frame, so the clock stops at the first render that follows it —
    // the first frame that can show data.
    const firstTile = await waitForFirstTile(map);
    const firstPaint = firstTile == null ? null : await waitForNextRender(map);
    const cold_time_to_meaningful_map_render_ms = firstPaint == null
      ? null : Math.round(firstPaint - t0);

    const coldIdle = await waitIdle(map);
    const cold_time_to_stable_viewport_ms = coldIdle.timedOut
      ? null : Math.round(coldIdle.at - t0);
    const cold_loaded_tile_bytes = sumTileTrafficBytes(sliceSinceLast());

    // --- Pan -----------------------------------------------------------------
    // "Horizontal and vertical panning operations were performed" — two
    // operations, so both are performed and each is timed on its own. A single
    // diagonal pan is one operation, and its recovery time is not the time
    // required after *a* pan operation.
    //
    // One full viewport each, not a token nudge: a 256 px pan at zoom 10 lands
    // inside tiles that are already loaded, so it fetched nothing and settled in
    // 6 ms — the phase reported zeros for every format.
    //
    // Recovery is the mean of the two, because the metric is defined per
    // operation. Requests and bytes are totals, because those are defined as
    // the volume generated while moving the map.
    const pans = [];
    for (const offset of [[VIEWPORT_WIDTH, 0], [0, VIEWPORT_HEIGHT]]) {
      const tPan = performance.now();
      map.panBy(offset, { animate: false });
      const panIdle = await waitIdle(map);
      const panSlice = sliceSinceLast();
      pans.push({
        recovery: panIdle.timedOut ? null : Math.round(panIdle.at - tPan),
        requests: countTileTraffic(panSlice),
        bytes: sumTileTrafficBytes(panSlice),
      });
    }
    const pan_recovery_time_ms = mean(pans.map((p) => p.recovery));
    const pan_new_tile_requests = pans.reduce((n, p) => n + p.requests, 0);
    const pan_loaded_tile_bytes = pans.reduce((n, p) => n + p.bytes, 0);

    // --- Zoom ----------------------------------------------------------------
    const tZoom = performance.now();
    map.jumpTo({ zoom: 14, animate: false });
    const zoomIdle = await waitIdle(map);
    const zoomSlice = sliceSinceLast();
    const zoom_recovery_time_ms = zoomIdle.timedOut ? null : Math.round(zoomIdle.at - tZoom);
    const zoom_new_tile_requests = countTileTraffic(zoomSlice);
    const zoom_loaded_tile_bytes = sumTileTrafficBytes(zoomSlice);

    // --- Layer toggle --------------------------------------------------------
    const toggleLayerId = pickToggleLayer(map);
    const toggle = toggleLayerId
      ? await measureLayerToggle(map, toggleLayerId)
      : { latency: null, style: null };
    const layer_toggle_latency_ms = toggle.latency;
    const layer_style_recalculation_time_ms = toggle.style;
    if (toggleLayerId) sliceSinceLast();

    const missing_tile_count = failedTiles.size + unidentifiedTileFailures;
    const render_success = renderSucceeded({
      firstRenderMs: cold_time_to_meaningful_map_render_ms,
      missingTiles: missing_tile_count,
      mapErrors: errors.mapErrors,
      tileRequests: tileTrafficMark(),
    });

    return {
      cold_time_to_meaningful_map_render_ms,
      cold_time_to_stable_viewport_ms,
      cold_loaded_tile_bytes,
      pan_recovery_time_ms,
      pan_new_tile_requests,
      pan_loaded_tile_bytes,
      zoom_recovery_time_ms,
      zoom_new_tile_requests,
      zoom_loaded_tile_bytes,
      layer_toggle_latency_ms,
      layer_style_recalculation_time_ms,
      missing_tile_count,
      console_error_count: errors.consoleErrors,
      // What the errors said. The count alone is unanalysable after the run.
      console_errors: errors.messages(),
      render_success,
      // Run provenance — recorded so results are attributable, not reported.
      gpu_renderer: gpuRenderer(),
      device_pixel_ratio: window.devicePixelRatio ?? null,
      viewport_width: VIEWPORT_WIDTH,
      viewport_height: VIEWPORT_HEIGHT,
    };
  } finally {
    errors.restore();
    try { map.remove(); } catch (_) { /* already torn down */ }
  }
}

/**
 * Time one disable/enable of a layer's visibility.
 *
 * layer_toggle_latency_ms is defined as the elapsed time between initiating *a*
 * visibility change and the completion of the corresponding visual update. Both
 * changes a user makes are measured — disabling a layer and enabling it again —
 * and each is timed from its own initiation, so the reported figure is the cost
 * of one change rather than of a whole cycle. Timing the round trip is what made
 * this metric read exactly 619 ms for all four formats: it was dominated by the
 * idle wait between the two.
 *
 * The visual update completes at the frame that reflects the change, which is
 * the next `render` after the style mutation — the same signal
 * cold_time_to_meaningful_map_render_ms uses for the same reason. It is
 * deliberately not `idle`: MapLibre defers `idle` behind a symbol-placement pass
 * carrying a fixed ~300 ms constant, and toggling visibility on an already
 * loaded style fetches nothing, so waiting for `idle` measured that constant and
 * nothing else — 309–312 ms alike for a 4 MB archive and a 564 MB one.
 *
 * Style recalculation still ends at `styledata`. That half was always correct:
 * it read 5–7 ms over the same runs and did vary with the work.
 */
export async function measureLayerToggle(map, layerId, timeoutMs = PHASE_TIMEOUT_MS) {
  const changes = [];
  for (const visibility of ['none', 'visible']) {
    // Both listeners are attached before the change, so neither event can fire
    // in the gap between mutating the style and awaiting it.
    const styled = waitFor(map, 'styledata', timeoutMs);
    const painted = waitForNextRender(map, timeoutMs);
    const tChange = performance.now();
    map.setLayoutProperty(layerId, 'visibility', visibility);
    const styledAt = await styled;
    const paintedAt = await painted;
    changes.push({
      style: styledAt == null ? null : Math.round(styledAt - tChange),
      latency: paintedAt == null ? null : Math.round(paintedAt - tChange),
    });
  }
  return {
    latency: mean(changes.map((c) => c.latency)),
    style: mean(changes.map((c) => c.style)),
  };
}

/**
 * Whether the map drew the data it was given.
 *
 * A first paint is not enough on its own. Louisiana mlt_pmtiles recorded
 * missing_tile_count: 0 and console_error_count: 0 on a run that issued zero
 * tile requests and transferred zero bytes — both literally true, because no
 * tile failed when none was attempted, and together the opposite of the
 * assurance the Rendering Correctness group exists to give. A run that asked for
 * no tiles has not rendered the dataset, whatever it painted.
 */
export function renderSucceeded({ firstRenderMs, missingTiles, mapErrors, tileRequests }) {
  return firstRenderMs !== null
    && missingTiles === 0
    && mapErrors === 0
    && tileRequests > 0;
}

/**
 * Count the errors the browser reports for the duration of a run.
 *
 * console_error_count is defined as "errors reported by the browser during the
 * visualization process", which is wider than console.error: an uncaught
 * exception or an unhandled promise rejection is reported by the browser
 * without necessarily passing through it.
 */
function installErrorCounters() {
  const original = console.error;
  const log = errorLog();
  const onError = (event) => log.record(event?.error ?? event?.message ?? 'window error');
  const onRejection = (event) => log.record(event?.reason ?? 'unhandled rejection');
  const state = {
    get consoleErrors() { return log.count; },
    messages: () => log.messages(),
    mapErrors: 0,
    restore() {
      console.error = original;
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
    },
  };
  console.error = (...args) => {
    log.record(...args);
    original.apply(console, args);
  };
  window.addEventListener('error', onError);
  window.addEventListener('unhandledrejection', onRejection);
  return state;
}

/** The GPU actually driving WebGL — hybrid laptops may not use the discrete one. */
function gpuRenderer() {
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
    if (!gl) return null;
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    return ext
      ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)
      : gl.getParameter(gl.RENDERER);
  } catch (_) {
    return null;
  }
}

function waitIdle(map, timeoutMs = PHASE_TIMEOUT_MS) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve({ at: performance.now(), timedOut: true }), timeoutMs);
    map.once('idle', () => {
      clearTimeout(timer);
      resolve({ at: performance.now(), timedOut: false });
    });
  });
}

/**
 * The first frame drawn after the caller's event of interest.
 *
 * MapLibre fires `render` once per painted frame, so the first one after tile
 * content has arrived is the first frame that can contain that content.
 */
function waitForNextRender(map, timeoutMs = PHASE_TIMEOUT_MS) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), timeoutMs);
    map.once('render', () => {
      clearTimeout(timer);
      resolve(performance.now());
    });
  });
}

/**
 * When an event arrives, or nothing if it never does.
 *
 * A timeout resolves as null rather than as the moment the timer fired: every
 * other phase reports null when it fails to settle, and resolving with a
 * timestamp turned a 30-second stall into a genuine-looking measurement.
 */
export function waitFor(map, event, timeoutMs = PHASE_TIMEOUT_MS) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), timeoutMs);
    map.once(event, () => {
      clearTimeout(timer);
      resolve(performance.now());
    });
  });
}

function waitForFirstTile(map, timeoutMs = PHASE_TIMEOUT_MS) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => { map.off('data', handler); resolve(null); }, timeoutMs);
    function handler(e) {
      if (e.dataType === 'source' && (e.tile || e.sourceDataType === 'content')) {
        clearTimeout(timer);
        map.off('data', handler);
        resolve(performance.now());
      }
    }
    map.on('data', handler);
  });
}

/**
 * The dataset's own layer, not the basemap's, and the same kind of layer on
 * every map.
 *
 * Both style builders append dataset layers after the basemap, so the topmost
 * layer of a given type is the data one. Toggling a basemap layer would measure
 * the wrong thing.
 *
 * Geometry is preferred fill -> line -> circle rather than taking the topmost
 * of the three, because layer_toggle_latency_ms is compared across datasets and
 * the topmost rule did not pick comparable layers. buildDynamicStyle appends
 * fill -> line -> point -> label, so a dataset carrying point layers (Saentis,
 * Amsterdam) had a sparse circle layer toggled while a polygon-only one
 * (Louisiana, Groundswell) had a dense fill: two numbers that are not
 * measurements of the same operation. Every dataset in the study has polygon
 * layers, so the fill is what all of them can be compared on.
 */
export function pickToggleLayer(map) {
  const style = map.getStyle();
  if (!style || !style.layers) return null;
  for (const type of ['fill', 'line', 'circle']) {
    for (let i = style.layers.length - 1; i >= 0; i -= 1) {
      if (style.layers[i].type === type) return style.layers[i].id;
    }
  }
  return null;
}
