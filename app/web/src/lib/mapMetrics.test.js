import { describe, expect, test } from 'vitest';
import {
  aggregateRuns, errorLog, mean, measureLayerToggle, pickToggleLayer,
  renderSucceeded,
  waitFor,
} from './mapMetrics';

// The paper defines pan recovery and toggle latency per operation, but the
// benchmark performs two of each -- a horizontal and a vertical pan, a disable
// and an enable. The reported figure is the mean of the operations, so it still
// means "one operation" the way the paper's definition does.
describe('mean', () => {
  test('averages the operations and rounds to whole milliseconds', () => {
    expect(mean([210, 190])).toBe(200);
    expect(mean([210, 191])).toBe(201);
  });

  test('ignores an operation that timed out rather than counting it as zero', () => {
    expect(mean([200, null])).toBe(200);
  });

  test('is null when every operation timed out, so a stall stays visible', () => {
    expect(mean([null, null])).toBeNull();
    expect(mean([])).toBeNull();
  });
});

describe('aggregateRuns', () => {
  const run = (over = {}) => ({
    cold_time_to_stable_viewport_ms: 100,
    cold_loaded_tile_bytes: 5000,
    missing_tile_count: 0,
    console_error_count: 0,
    render_success: true,
    gpu_renderer: 'AMD Radeon 780M',
    device_pixel_ratio: 1.5,
    ...over,
  });

  test('reports the median of an odd number of runs', () => {
    const out = aggregateRuns([
      run({ cold_time_to_stable_viewport_ms: 300 }),
      run({ cold_time_to_stable_viewport_ms: 100 }),
      run({ cold_time_to_stable_viewport_ms: 200 }),
    ]);

    expect(out.cold_time_to_stable_viewport_ms).toBe(200);
  });

  test('averages the middle two for an even number of runs', () => {
    const out = aggregateRuns([
      run({ cold_time_to_stable_viewport_ms: 100 }),
      run({ cold_time_to_stable_viewport_ms: 300 }),
    ]);

    expect(out.cold_time_to_stable_viewport_ms).toBe(200);
  });

  test('records the observed spread and the number of runs', () => {
    const out = aggregateRuns([
      run({ cold_time_to_stable_viewport_ms: 100 }),
      run({ cold_time_to_stable_viewport_ms: 250 }),
      run({ cold_time_to_stable_viewport_ms: 400 }),
    ]);

    expect(out.runs).toBe(3);
    expect(out.spread.cold_time_to_stable_viewport_ms).toEqual({ min: 100, max: 400 });
  });

  test('ignores runs where a phase timed out', () => {
    const out = aggregateRuns([
      run({ cold_time_to_stable_viewport_ms: null }),
      run({ cold_time_to_stable_viewport_ms: 100 }),
      run({ cold_time_to_stable_viewport_ms: 300 }),
    ]);

    expect(out.cold_time_to_stable_viewport_ms).toBe(200);
  });

  test('is null when every run timed out', () => {
    const out = aggregateRuns([
      run({ cold_time_to_stable_viewport_ms: null }),
      run({ cold_time_to_stable_viewport_ms: null }),
    ]);

    expect(out.cold_time_to_stable_viewport_ms).toBeNull();
  });

  test('counts a format as successful only if every run succeeded', () => {
    expect(aggregateRuns([run(), run()]).render_success).toBe(true);
    expect(aggregateRuns([run(), run({ render_success: false })]).render_success).toBe(false);
  });

  test('reports the worst error counts, not the typical ones', () => {
    const out = aggregateRuns([
      run({ missing_tile_count: 0, console_error_count: 0 }),
      run({ missing_tile_count: 4, console_error_count: 2 }),
      run({ missing_tile_count: 0, console_error_count: 0 }),
    ]);

    expect(out.missing_tile_count).toBe(4);
    expect(out.console_error_count).toBe(2);
  });

  test('carries run provenance through unchanged', () => {
    const out = aggregateRuns([run(), run()]);

    expect(out.gpu_renderer).toBe('AMD Radeon 780M');
    expect(out.device_pixel_ratio).toBe(1.5);
  });
});

// Every phase that fails to settle contributes nothing rather than the timeout
// duration, so a stall is distinguishable from a slow result. layer_style_
// recalculation_time_ms was the one metric that broke the rule: its wait
// resolved with the current time when the timer fired.
describe('waitFor', () => {
  const emitter = (fires) => ({
    once: (_event, cb) => { if (fires) setTimeout(cb, 0); },
  });

  test('resolves with a timestamp when the event arrives', async () => {
    await expect(waitFor(emitter(true), 'styledata', 50)).resolves.toBeTypeOf('number');
  });

  test('resolves with nothing when the event never arrives', async () => {
    await expect(waitFor(emitter(false), 'styledata', 5)).resolves.toBeNull();
  });
});

// layer_toggle_latency_ms read 309-312 ms for every dataset and every format,
// across archives differing 130x in size. The cause was its completion signal:
// MapLibre's `idle` is gated by a symbol-placement pass carrying a fixed ~300 ms
// constant, so the metric was that constant and nothing else. The paper defines
// it as ending at "completion of the corresponding visual update", which is the
// frame that shows the change.
describe('measureLayerToggle', () => {
  const fakeMap = ({ styledataAfter, renderAfter, idleAfter }) => ({
    changes: [],
    once(event, cb) {
      const delay = { styledata: styledataAfter, render: renderAfter, idle: idleAfter }[event];
      if (delay != null) setTimeout(cb, delay);
    },
    setLayoutProperty(id, prop, value) { this.changes.push([id, prop, value]); },
  });

  test('times the visual update, not MapLibre\'s placement debounce', async () => {
    const map = fakeMap({ styledataAfter: 1, renderAfter: 5, idleAfter: 300 });

    const result = await measureLayerToggle(map, 'some-layer');

    expect(result.latency).toBeLessThan(50);
  });

  test('measures the disable and the enable, and reports one operation', async () => {
    const map = fakeMap({ styledataAfter: 1, renderAfter: 5, idleAfter: 300 });

    await measureLayerToggle(map, 'some-layer');

    expect(map.changes).toEqual([
      ['some-layer', 'visibility', 'none'],
      ['some-layer', 'visibility', 'visible'],
    ]);
  });

  test('keeps style recalculation on styledata, which already discriminated', async () => {
    const map = fakeMap({ styledataAfter: 1, renderAfter: 40, idleAfter: 300 });

    const result = await measureLayerToggle(map, 'some-layer');

    expect(result.style).toBeLessThan(result.latency);
  });

  test('a change whose frame never arrives is null, not the timeout', async () => {
    const map = fakeMap({ styledataAfter: 1, renderAfter: null, idleAfter: null });

    const result = await measureLayerToggle(map, 'some-layer', 5);

    expect(result.latency).toBeNull();
  });
});

// Louisiana mlt_pmtiles, 2026-08-28: zero tile requests, zero bytes, zero
// errors -- and two of the three Rendering Correctness metrics reporting no
// problems. A reader of missing_tile_count: 0 and console_error_count: 0 would
// conclude the map rendered perfectly. Nothing failed to load because nothing
// was ever attempted.
describe('renderSucceeded', () => {
  const clean = {
    firstRenderMs: 30, missingTiles: 0, mapErrors: 0, tileRequests: 12,
  };

  test('a run that drew tiles without failures succeeded', () => {
    expect(renderSucceeded(clean)).toBe(true);
  });

  test('a run that requested no tiles is not a successful render', () => {
    expect(renderSucceeded({ ...clean, tileRequests: 0 })).toBe(false);
  });

  test('a run that never painted is not a successful render', () => {
    expect(renderSucceeded({ ...clean, firstRenderMs: null })).toBe(false);
  });

  test('a run with a failed tile or a map error is not a successful render', () => {
    expect(renderSucceeded({ ...clean, missingTiles: 1 })).toBe(false);
    expect(renderSucceeded({ ...clean, mapErrors: 1 })).toBe(false);
  });
});

// layer_toggle_latency_ms is one of the paper's eighteen and is compared across
// datasets. It was toggling a different kind of layer on each map: the picker
// took the topmost fill/line/circle, and buildDynamicStyle appends
// fill -> line -> point -> label, so a dataset carrying point layers (Saentis,
// Amsterdam) had a sparse circle layer toggled while a polygon-only one
// (Louisiana, Groundswell) had a dense fill. Those two numbers are not
// measurements of the same operation. Every study dataset has polygon layers,
// so the fill is the one thing all four can be compared on.
describe('pickToggleLayer', () => {
  const styled = (...layers) => ({ getStyle: () => ({ layers }) });

  test('toggles the fill even when a point layer sits above it', () => {
    const map = styled(
      { id: 'wetlands-fill', type: 'fill' },
      { id: 'wetlands-outline', type: 'line' },
      { id: 'survey-points', type: 'circle' },
      { id: 'survey-labels', type: 'symbol' },
    );

    expect(pickToggleLayer(map)).toBe('wetlands-fill');
  });

  test('falls back to a line, then a circle, when the map has no polygons', () => {
    expect(pickToggleLayer(styled(
      { id: 'faults', type: 'line' },
      { id: 'dip-symbols', type: 'circle' },
    ))).toBe('faults');

    expect(pickToggleLayer(styled({ id: 'dip-symbols', type: 'circle' }))).toBe('dip-symbols');
  });

  test('ignores the basemap below the dataset layers', () => {
    const map = styled(
      { id: 'background', type: 'background' },
      { id: 'basemap-water', type: 'fill' },
      { id: 'geology-fill', type: 'fill' },
    );

    expect(pickToggleLayer(map)).toBe('geology-fill');
  });

  test('is null when the style carries nothing togglable', () => {
    expect(pickToggleLayer(styled({ id: 'background', type: 'background' }))).toBeNull();
    expect(pickToggleLayer({ getStyle: () => null })).toBeNull();
  });
});

// console_error_count is one of the paper's eighteen, and it recorded a number
// and never the text. Playwright's pageerror listener catches uncaught
// exceptions, not console.error calls, so a result of `console_error_count: 4`
// could not be explained after the fact without reproducing the whole run --
// which is how the attribute-less catch-all style stayed hidden until someone
// read the code instead of the metrics.
describe('errorLog', () => {
  test('keeps the text of each distinct error, with how often it occurred', () => {
    const log = errorLog();

    log.record('Failed to load tile');
    log.record('Failed to load tile');
    log.record('style is not defined');

    expect(log.count).toBe(3);
    expect(log.messages()).toEqual([
      { message: 'Failed to load tile', count: 2 },
      { message: 'style is not defined', count: 1 },
    ]);
  });

  test('reads an Error by name and message, not as [object Object]', () => {
    const log = errorLog();

    log.record(new TypeError('sourceUrl is not defined'));

    expect(log.messages()[0].message).toBe('TypeError: sourceUrl is not defined');
  });

  test('a render loop erroring every frame cannot fill the protocol', () => {
    const log = errorLog(2);

    log.record('first');
    log.record('second');
    log.record('third');
    log.record('fourth');

    expect(log.count).toBe(4);
    const messages = log.messages();
    expect(messages.slice(0, 2)).toEqual([
      { message: 'first', count: 1 },
      { message: 'second', count: 1 },
    ]);
    // Truncation is stated rather than left to be inferred by comparing the
    // sum of the counts against console_error_count.
    expect(messages[2].message).toMatch(/truncated/i);
  });
});

// console_error_count is reported as the worst run rather than the typical one,
// so the messages have to survive aggregation the same way. Left to the numeric
// path they came out null, because an array is not a number.
describe('aggregateRuns with console errors', () => {
  const run = (count, errors) => ({
    console_error_count: count, console_errors: errors,
  });

  test('carries the messages from every run, not just the last', () => {
    const out = aggregateRuns([
      run(1, [{ message: 'tile failed', count: 1 }]),
      run(0, []),
      run(2, [{ message: 'style missing', count: 2 }]),
    ]);

    expect(out.console_errors).toEqual([
      { message: 'tile failed', count: 1 },
      { message: 'style missing', count: 2 },
    ]);
  });

  test('reports the worst occurrence of a message, matching the count metric', () => {
    const out = aggregateRuns([
      run(1, [{ message: 'tile failed', count: 1 }]),
      run(3, [{ message: 'tile failed', count: 3 }]),
    ]);

    expect(out.console_error_count).toBe(3);
    expect(out.console_errors).toEqual([{ message: 'tile failed', count: 3 }]);
  });
});
