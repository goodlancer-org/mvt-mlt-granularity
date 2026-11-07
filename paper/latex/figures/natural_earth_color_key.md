# Color key for natural_earth_mvt_mlt_comparison.png

**Natural Earth publishes data, not a vector style, so none of these colors is official.** They follow general cartographic convention (blue water, pale land, tan urban areas, green parks, red/orange/yellow roads by importance, purple state borders, gray county borders), chosen so that no two legend entries share a color.
- Each feature is colored by its own class (`featurecla`, or `type` for roads); the **Source** column says `convention` for every assigned color.
- Values not listed in the convention table fall back to gray `#9a9a9a` and are marked `not official`.
- Admin polygons (countries, states, counties) are drawn as outlines only; their fill would hide everything under them.
- Draw order is by class (ocean, land, lakes and urban areas, borders, coast and rivers, roads, ports and airports, places).
- The tile marker in the locator grid is magenta `#e6007e`, a color used by no map class.
- Fill / outline are hex colors. **Pattern** = the figure draws a hatch in the pattern color. **Line** = drawn as a line, not a filled area.
- **not official** = no official color exists for this value; the figure uses the neutral fallback color. These are NOT official colors.
- **MVT vs MLT attribute types differ** in the displayed tiles: `hydrography.scalerank` is float in MVT and str in MLT (5 features); `hydrography.scalerank` is int in MVT and str in MLT (107 features). Values are equal as text; only the stored type differs.
- Counts are features in the three displayed tiles (z5 / z7 / z9).

## Land and urban areas  (`land_use`)

| Value | Meaning | Fill | Outline | Style | Source | z5 / z7 / z9 |
|---|---|---|---|---|---|---|
| Urban area | built-up urban area | `#e2cfb4` | `#e2cfb4` | solid | convention | 78 / 29 / 6 |
| (no class) |  | — | `#9a9a9a` | not official |  | 43 / 10 / 4 |
| Land | land mass | `#f3efe4` | `#f3efe4` | solid | convention | 29 / 12 / 6 |
| Coastline | coastline | — | `#4f7fa6` | line | convention | 26 / 8 / 4 |
| National Park Service | US National Park Service area | `#cfe5c3` | `#9cc58a` | solid | convention | 10 / 3 / 0 |
| Minor coastline | minor coastline | — | `#4f7fa6` | line | convention | 8 / 0 / 0 |

## Water  (`hydrography`)

| Value | Meaning | Fill | Outline | Style | Source | z5 / z7 / z9 |
|---|---|---|---|---|---|---|
| River | river | — | `#5b9bd5` | line | convention | 72 / 11 / 2 |
| Land | land mass | — | `#9a9a9a` | not official |  | 25 / 6 / 2 |
| Ocean | ocean | `#b9d7ee` | `#b9d7ee` | solid | convention | 2 / 2 / 2 |
| Lake Centerline | centre line through a lake | — | `#5b9bd5` | line | convention | 6 / 0 / 0 |
| Lake | lake | `#8fc1e6` | `#8fc1e6` | solid | convention | 4 / 0 / 0 |
| Reservoir | reservoir | `#8fc1e6` | `#8fc1e6` | solid | convention | 3 / 0 / 0 |

## Boundaries  (`boundaries`)

| Value | Meaning | Fill | Outline | Style | Source | z5 / z7 / z9 |
|---|---|---|---|---|---|---|
| Admin-2 scale rank | county area / label point | — | `#b5b5b5` | line | convention | 1746 / 353 / 95 |
| Admin-2 boundary | county border | — | `#b5b5b5` | line | convention | 460 / 76 / 16 |
| Admin-0 scale ranks | country area / label point | — | `#222222` | line | convention | 81 / 22 / 10 |
| Admin-0 country | country area | — | `#222222` | line | convention | 35 / 35 / 35 |
| Admin-2 boundary indicator | county border (indicator) | — | `#b5b5b5` | line | convention | 66 / 19 / 11 |
| Admin-1 scale rank | state / province label point | — | `#8e5ea2` | line | convention | 54 / 9 / 2 |
| Admin-1 states provinces scale rank | state / province area | — | `#8e5ea2` | line | convention | 39 / 13 / 5 |
| Admin-1 states provinces minor islands | state / province, minor islands | — | `#8e5ea2` | line | convention | 39 / 13 / 5 |
| Admin-1 boundary | state / province border | — | `#8e5ea2` | line | convention | 28 / 8 / 2 |
| Admin-1 boundary indicator | state / province border (indicator) | — | `#8e5ea2` | line | convention | 16 / 10 / 4 |
| Admin-1 states provinces | state / province area | — | `#8e5ea2` | line | convention | 11 / 6 / 2 |
| Admin-1 states provinces lakes | state / province incl. lakes | — | `#8e5ea2` | line | convention | 11 / 6 / 2 |
| Admin-1 statistical meta bounds | statistical region border | — | `#8e5ea2` | line | convention | 4 / 4 / 0 |
| Admin-1 statistical boundary | statistical region border | — | `#8e5ea2` | line | convention | 2 / 2 / 0 |
| Admin-0 map subunit | country map subunit | — | `#222222` | line | convention | 1 / 1 / 1 |
| Admin-0 map unit | country map unit | — | `#222222` | line | convention | 1 / 1 / 1 |
| Admin-0 sovereignty | sovereign state area | — | `#222222` | line | convention | 1 / 1 / 1 |

## Roads, rail, ports, airports  (`transportation`)

| Value | Meaning | Fill | Outline | Style | Source | z5 / z7 / z9 |
|---|---|---|---|---|---|---|
| Other Paved | other paved road | — | `#b9ad96` | line | convention | 812 / 694 / 364 |
| Secondary | secondary road | — | `#f4d03f` | line | convention | 671 / 319 / 77 |
| Secondary Highway | secondary highway | — | `#f4d03f` | line | convention | 439 / 142 / 21 |
| Primary | primary road | — | `#f0a030` | line | convention | 407 / 138 / 20 |
| Freeway | freeway | — | `#d94f30` | line | convention | 275 / 169 / 77 |
| Major Highway | major highway | — | `#d94f30` | line | convention | 235 / 111 / 43 |
| Railroad | railroad | — | `#555555` | line | convention | 80 / 38 / 17 |
| Tollway | toll road | — | `#d94f30` | line | convention | 35 / 52 / 27 |
| Beltway | beltway (ring road) | — | `#d94f30` | line | convention | 26 / 5 / 3 |
| Port | port | — | `#1f4e79` | point | convention | 18 / 6 / 3 |
| Airport | airport | — | `#2e7d32` | point | convention | 11 / 4 / 2 |
| Ferry | ferry route | — | `#7e57c2` | line | convention | 7 / 2 / 0 |
| Road | road | — | `#b9ad96` | line | convention | 6 / 1 / 1 |
| Ferry Route | ferry route | — | `#7e57c2` | line | convention | 3 / 2 / 0 |
| Bypass | bypass | — | `#f0a030` | line | convention | 1 / 0 / 0 |

## Places  (`places`)

| Value | Meaning | Fill | Outline | Style | Source | z5 / z7 / z9 |
|---|---|---|---|---|---|---|
| Admin-2 scale rank | county area / label point | — | `#b5b5b5` | line | convention | 483 / 81 / 18 |
| Populated place | city / town | — | `#7a1f1f` | point | convention | 70 / 14 / 6 |
| Admin-1 scale rank | state / province label point | — | `#8e5ea2` | line | convention | 54 / 9 / 2 |
| Admin-0 scale ranks | country area / label point | — | `#222222` | line | convention | 33 / 6 / 2 |
| Admin-1 capital | state / province capital | — | `#444444` | point | convention | 12 / 4 / 0 |
| Timezone | time-zone area | — | `#d8d8d8` | line | convention | 2 / 1 / 1 |
| Admin-0 capital | national capital | — | `#000000` | point | convention | 2 / 0 / 0 |
