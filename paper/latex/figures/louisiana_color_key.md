# Color key for louisiana_mvt_mlt_comparison.png

Colors are taken from the official **USFWS National Wetlands Inventory** map-service renderer (field `WETLAND_TYPE`): https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0 . Legend page: https://www.fws.gov/node/268025 .
- Every official class uses a `#6e6e6e` (RGB 110,110,110) outline.
- The official renderer also defines **Other** `#b38753`; it does not occur in the three displayed tiles.
- Meanings are my plain-language summaries, not USFWS text.
- The tile marker in the locator grid is magenta `#e6007e`, a color used by no wetland class.
- Fill / outline are hex colors. **Pattern** = the figure draws a hatch in the pattern color. **Line** = drawn as a line, not a filled area.
- **not official** = no official color exists for this value; the figure uses the neutral fallback color. These are NOT official colors.
- Counts are features in the three displayed tiles (z10 / z12 / z14).

## Wetlands (USFWS National Wetlands Inventory)  (`hydrography`)

| Value | Meaning | Fill | Outline | Style | Source | z10 / z12 / z14 |
|---|---|---|---|---|---|---|
| Estuarine and Marine Wetland | tidal wetland (salt / brackish) | `#66c2a5` | `#6e6e6e` | solid | NWI renderer | 1373 / 786 / 296 |
| Estuarine and Marine Deepwater | open tidal water (deepwater habitat) | `#007c87` | `#6e6e6e` | solid | NWI renderer | 229 / 64 / 1071 |
| Freshwater Forested/Shrub Wetland | swamp: trees and shrubs on freshwater | `#008737` | `#6e6e6e` | solid | NWI renderer | 179 / 0 / 0 |
| Freshwater Emergent Wetland | freshwater marsh (non-woody plants) | `#7fc319` | `#6e6e6e` | solid | NWI renderer | 41 / 0 / 0 |
| (no wetland class) | polygon without a wetland class | `#d9d9d9` | `#6e6e6e` | not official |  | 8 / 5 / 5 |
| Riverine | river or stream channel | `#008fbf` | `#6e6e6e` | solid | NWI renderer | 14 / 0 / 0 |
| Freshwater Pond | freshwater pond | `#678bc0` | `#6e6e6e` | solid | NWI renderer | 10 / 0 / 0 |
| Lake | lake | `#12007c` | `#6e6e6e` | solid | NWI renderer | 7 / 0 / 0 |
