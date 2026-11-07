# Color key for netherlands_mvt_mlt_comparison.png

Colors are taken from the official **BGT|IMGeo standaardvisualisatie 2.3** (Geonovum), SLD file set `sld-standaardvisualisatie.zip`, https://github.com/Geonovum/IMGeo/tree/master/visualisatie/2.3 (spec: https://docs.geostandaarden.nl/bgt/vv-hr-visualisatie-20180906/). Each feature is colored by its own attribute value (`bgt-fysiekVoorkomen`, `bgt-functie`, `bgt-type`, ...), not by layer.
- Official road and white-filled land-use classes also have a gray `#535353` outline.
- Some official colors coincide (e.g. grass and bank / ditch edge are both `#c9eb70`; local road, cycle path and paved yard are all white); the legend merges classes that look the same into one entry.
- The tile marker in the locator grid is magenta `#e6007e`, a color used by no map class.
- Drawing order in the figure is my own, not the official drawing sequence.
- Fill / outline are hex colors. **Pattern** = the figure draws a hatch in the pattern color. **Line** = drawn as a line, not a filled area.
- **not official** = no official color exists for this value; the figure uses the neutral fallback color. These are NOT official colors.
- Counts are features in the three displayed tiles (z12 / z13 / z14).

## Land use  (`land_use`)

| Value | Meaning | Fill | Outline | Style | Source | z12 / z13 / z14 |
|---|---|---|---|---|---|---|
| groenvoorziening | green space | `#8ca800` | `#8ca800` | solid | sld-0010 | 3583 / 2836 / 5077 |
| erf | yard / plot | `#ffffff` | `#535353` | solid | sld-0011 | 5597 / 2513 / 1799 |
| grasland overig | grassland (other) | `#c9eb70` | `#c9eb70` | solid | sld-0010 | 967 / 549 / 98 |
| (no attribute value) |  | `#8a8a8a` | `#535353` | not official |  | 1428 / 12 / 0 |
| onverhard | unpaved | `#f3f5f6` | `#f3f5f6` | solid | sld-0011 | 138 / 84 / 780 |
| grasland agrarisch | grassland (agricultural) | `#c9eb70` | `#c9eb70` | solid | sld-0010 | 677 / 224 / 2 |
| open verharding | open paving | `#ffffff` | `#535353` | solid | sld-0011 | 388 / 367 / 117 |
| zand | sand | `#ffff99` | `#ffff99` | solid | sld-0011 | 292 / 192 / 2 |
| transitie | transition (edge between data sets) | `#f2f2f2` | `#535353` | solid | sld-0010 | 91 / 47 / 30 |
| gesloten verharding | closed paving | `#ffffff` | `#535353` | solid | sld-0011 | 36 / 62 / 48 |
| bouwland | arable land | `#ffffcc` | `#ffffcc` | solid | sld-0010 | 110 / 2 / 0 |
| boomteelt | tree nursery | — | `#ffffcc` | pattern `.....` | sld-0010 | 51 / 30 / 30 |
| loofbos | deciduous forest | — | `#8ca800` | pattern `ooo` | sld-0010 | 82 / 15 / 0 |
| struiken | shrubs | — | `#8ca800` | pattern `xxx` | sld-0010 | 41 / 13 / 26 |
| houtwal | wooded bank | `#8ca800` | `#8ca800` | solid | sld-0010 | 33 / 19 / 0 |
| half verhard | semi-paved | `#ffffff` | `#535353` | solid | sld-0011 | 21 / 12 / 7 |
| gemengd bos | mixed forest | — | `#8ca800` | pattern `ooo` | sld-0010 | 18 / 10 / 0 |
| fruitteelt | orchard | — | `#ffffcc` | pattern `.....` | sld-0010 | 10 / 0 / 0 |
| moeras | marsh | — | `#c9eb70` | pattern `---` | sld-0010 | 4 / 0 / 0 |
| rietland | reed bed | — | `#c9eb70` | pattern `|||` | sld-0010 | 2 / 1 / 0 |
| naaldbos | coniferous forest | — | `#8ca800` | pattern `ooo` | sld-0010 | 1 / 0 / 0 |

## Water  (`hydrography`)

| Value | Meaning | Fill | Outline | Style | Source | z12 / z13 / z14 |
|---|---|---|---|---|---|---|
| waterloop | watercourse | `#73e9ff` | `#73e9ff` | solid | sld-0030 | 445 / 259 / 2 |
| oever, slootkant | bank / ditch edge | `#C9EB70` | `#C9EB70` | solid | sld-0031 | 409 / 230 / 0 |
| watervlakte | water surface | `#bee8ff` | `#bee8ff` | solid | sld-0030 | 215 / 116 / 27 |
| greppel, droge sloot | dry ditch / gully | — | `#73e9ff` | line | sld-0030 | 26 / 16 / 2 |
| slik | mudflat | `#73e9ff` | `#73e9ff` | solid | sld-0031 | 2 / 0 / 0 |

## Functional areas  (`functioneelgebied`)

| Value | Meaning | Fill | Outline | Style | Source | z12 / z13 / z14 |
|---|---|---|---|---|---|---|
| kering | barrier (dike / flood defence) | — | `#002750` | line | sld-0060 | 180 / 93 / 22 |
| niet-bgt | not a BGT class (generic) | — | `#9a9a9a` | not official |  | 136 / 89 / 59 |

## Roads & rail  (`transportation`)

| Value | Meaning | Fill | Outline | Style | Source | z12 / z13 / z14 |
|---|---|---|---|---|---|---|
| voetpad | footpath | `#ff9999` | `#535353` | solid | sld-0021 | 1514 / 3628 / 5624 |
| rijbaan lokale weg | local road carriageway | `#ffffff` | `#535353` | solid | sld-0021 | 3154 / 3056 / 2401 |
| parkeervlak | parking area | `#ffffff` | `#535353` | solid | sld-0021 | 90 / 441 / 1891 |
| transitie | transition (edge between data sets) | `#f2f2f2` | `#535353` | solid | sld-0021 | 294 / 364 / 1557 |
| fietspad | cycle path | `#ffffff` | `#535353` | solid | sld-0021 | 482 / 658 / 468 |
| trein | train track (line) | — | `#535353` | line | sld-0020 | 424 / 446 / 532 |
| verkeerseiland | traffic island | `#ff9999` | `#ff9999` | solid | sld-0022 | 8 / 37 / 582 |
| voetpad op trap | footpath on stairs | `#ff9999` | `#535353` | solid | sld-0021 | 8 / 32 / 433 |
| berm | verge | `#ff9999` | `#ff9999` | solid | sld-0022 | 223 / 200 / 45 |
| voetgangersgebied | pedestrian area | `#ff9999` | `#535353` | solid | sld-0021 | 110 / 155 / 119 |
| inrit | driveway | `#ffffff` | `#535353` | solid | sld-0021 | 43 / 57 / 188 |
| OV-baan | public-transport lane | `#CCCCCC` | `#535353` | solid | sld-0021 | 79 / 104 / 100 |
| (no attribute value) |  | `#8a8a8a` | `#535353` | not official |  | 68 / 92 / 41 |
| rijbaan regionale weg | regional road carriageway | `#ffaa00` | `#535353` | solid | sld-0021 | 26 / 113 / 37 |
| spoorbaan | railway bed | `#c0c0c0` | `#535353` | solid | sld-0021 | 60 / 55 / 42 |
| woonerf | shared-space street | `#ffffff` | `#535353` | solid | sld-0021 | 16 / 16 / 20 |
| rijbaan autoweg | motorway-type road carriageway | `#e60000` | `#535353` | solid | sld-0021 | 22 / 30 / 0 |
| overweg | level crossing | `#c0c0c0` | `#535353` | solid | sld-0021 | 0 / 0 / 18 |
| ruiterpad | bridle path | `#ffffff` | `#535353` | solid | sld-0021 | 0 / 1 / 3 |

## Infrastructure  (`infrastructure`)

| Value | Meaning | Fill | Outline | Style | Source | z12 / z13 / z14 |
|---|---|---|---|---|---|---|
| (no attribute value) |  | `#8a8a8a` | `#535353` | not official |  | 2151 / 1648 / 4475 |
| kolk | street gully / drain | `#8a8a8a` | `#535353` | not official |  | 372 / 28 / 0 |
| lichtmast | lamp post | `#8a8a8a` | `#535353` | not official |  | 243 / 28 / 0 |
| inspectie- / rioolput | manhole | `#8a8a8a` | `#535353` | not official |  | 103 / 7 / 0 |
| verkeersbordpaal | traffic-sign post | `#8a8a8a` | `#535353` | not official |  | 102 / 0 / 0 |
| verkeersbord | traffic sign | `#8a8a8a` | `#535353` | not official |  | 84 / 0 / 0 |
| afsluitpaal | bollard | `#8a8a8a` | `#535353` | not official |  | 58 / 0 / 0 |
| speelvoorziening | playground equipment | `#8a8a8a` | `#535353` | not official |  | 54 / 0 / 0 |
| brandkraan / -put | fire hydrant | `#8a8a8a` | `#535353` | not official |  | 24 / 2 / 0 |
| container | container | `#8a8a8a` | `#535353` | not official |  | 19 / 0 / 0 |
| afvalbak | waste bin | `#8a8a8a` | `#535353` | not official |  | 18 / 0 / 0 |
| bank | bench | `#8a8a8a` | `#535353` | not official |  | 17 / 0 / 0 |
| verkeersregelinstallatiepaal | traffic-light pole | `#8a8a8a` | `#535353` | not official |  | 15 / 0 / 0 |
| wegwijzer | signpost | `#8a8a8a` | `#535353` | not official |  | 7 / 7 / 0 |
| elektrakast | electrical cabinet | `#8a8a8a` | `#535353` | not official |  | 11 / 0 / 0 |
| portaal | gantry | `#8a8a8a` | `#535353` | not official |  | 11 / 0 / 0 |
| fietsenrek | bicycle rack | `#8a8a8a` | `#535353` | not official |  | 7 / 0 / 0 |
| CAI-kast | cable-TV cabinet | `#8a8a8a` | `#535353` | not official |  | 6 / 0 / 0 |
| rioolkast | sewer cabinet | `#8a8a8a` | `#535353` | not official |  | 5 / 1 / 0 |
| hek | fence | — | `#000000` | line | sld-0045 | 2 / 0 / 4 |
| waterleidingput | water-main pit | `#8a8a8a` | `#535353` | not official |  | 6 / 0 / 0 |
| verklikker transportleiding | pipeline marker | `#8a8a8a` | `#535353` | not official |  | 5 / 0 / 0 |
| drukknoppaal | push-button pole | `#8a8a8a` | `#535353` | not official |  | 5 / 0 / 0 |
| lichtpunt | light point | `#8a8a8a` | `#535353` | not official |  | 5 / 0 / 0 |
| duiker | culvert | — | `#CC0000` | line | sld-0041 | 4 / 0 / 0 |
| kunstobject | art object | `#8a8a8a` | `#535353` | not official |  | 4 / 0 / 0 |
| waarschuwingshek | warning fence | `#8a8a8a` | `#535353` | not official |  | 1 / 1 / 0 |
| verkeersregelinstallatiekast | traffic-control cabinet | `#8a8a8a` | `#535353` | not official |  | 2 / 0 / 0 |
| openbare verlichtingkast | street-lighting cabinet | `#8a8a8a` | `#535353` | not official |  | 1 / 1 / 0 |
| draadraster | wire grid fence | — | `#000000` | line | sld-0045 | 2 / 0 / 0 |
| abri | bus shelter | `#8a8a8a` | `#535353` | not official |  | 2 / 0 / 0 |
| informatiebord | information board | `#8a8a8a` | `#535353` | not official |  | 1 / 0 / 0 |
| haltepaal | stop pole | `#8a8a8a` | `#535353` | not official |  | 1 / 0 / 0 |
| telpaal | counting post | `#8a8a8a` | `#535353` | not official |  | 1 / 0 / 0 |
| sirene | siren | `#8a8a8a` | `#535353` | not official |  | 1 / 0 / 0 |

## Road furniture  (`weginrichtingselement`)

| Value | Meaning | Fill | Outline | Style | Source | z12 / z13 / z14 |
|---|---|---|---|---|---|---|
| rooster | grate | `#8a8a8a` | `#535353` | not official |  | 10 / 10 / 0 |
| balustrade | balustrade | `#8a8a8a` | `#535353` | not official |  | 9 / 7 / 0 |
| geleideconstructie | guard rail | `#8a8a8a` | `#535353` | not official |  | 2 / 1 / 0 |

## Unclassified objects  (`ongeclassificeerdobject`)

| Value | Meaning | Fill | Outline | Style | Source | z12 / z13 / z14 |
|---|---|---|---|---|---|---|
| (all features) |  | `#ffffff` | `#535353` | solid | sld-0900 | 14 / 21 / 4 |

## Buildings  (`buildings`)

| Value | Meaning | Fill | Outline | Style | Source | z12 / z13 / z14 |
|---|---|---|---|---|---|---|
| (no attribute: ordinary building / pand) |  | `#cc0000` | `#D73939` | solid | sld-0044 | 1708 / 3490 / 12240 |
| niet-bgt | not a BGT class (generic) | `#cc0000` | `#D73939` | solid | sld-0044 | 1 / 2 / 39 |
| lage trafo | low transformer station | `#CC0000` | `#CC0000` | solid | sld-0043 | 0 / 0 / 22 |
| overkapping | canopy / covered structure | `#CC0000` | `#CC0000` | solid | sld-0043 | 6 / 7 / 8 |
| open loods | open shed | `#CC0000` | `#CC0000` | solid | sld-0043 | 0 / 1 / 7 |
| transitie | transition (edge between data sets) | `#cc0000` | `#D73939` | solid | sld-0044 | 0 / 0 / 6 |
| bassin | basin | `#BEE8FF` | `#CC0000` | solid | sld-0043 | 3 / 0 / 0 |

## Other separations (fences, walls)  (`overigescheiding`)

| Value | Meaning | Fill | Outline | Style | Source | z12 / z13 / z14 |
|---|---|---|---|---|---|---|
| hek | fence | — | `#000000` | line | sld-0080 | 2 / 0 / 4 |

## Name-label points  (`openbareruimtelabel`)

| Value | Meaning | Fill | Outline | Style | Source | z12 / z13 / z14 |
|---|---|---|---|---|---|---|
| Weg | road | — | `#000000` | point | sld-0071 | 2947 / 1493 / 740 |
| Terrein | terrain | — | `#000000` | point | sld-0071 | 50 / 23 / 13 |
| Water | water | — | `#002750` | point | sld-0071 | 49 / 34 / 0 |
| Kunstwerk | engineering structure | — | `#000000` | point | sld-0071 | 27 / 15 / 2 |
| Landschappelijk gebied | landscape area | — | `#425000` | point | sld-0071 | 8 / 0 / 0 |
| Administratief gebied | administrative area | — | `#000000` | point | sld-0071 | 5 / 1 / 1 |
