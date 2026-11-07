# Color key for swisstopo_mvt_mlt_comparison.png

**swisstopo_mountains_vector is a geological map.** It is the Swisstopo *Structural Map of the Helvetic Zone of the Swiss Alps* (Special Geological Map No. 128, 1:100,000, Pfiffner et al., 2011). The tile layer `terrain` is built from the source layer `STRUCTHELV_POLYGON_MAIN` (2,959 polygons, 48 geological units). Each polygon is one geological map unit: a rock formation, deposit or tectonic unit.
- **The tiles themselves store no rock type.** The conversion profile sets `fields: []`, so each tile feature has only geometry and a numeric id. The rock unit of each area in the figure was recovered by matching the tile polygon to the polygon of the original Swisstopo shapefile (`128-V-1-0/Data/Shapefiles/STRUCTHELV_POLYGON_MAIN.shp`, found in the local unzip cache of `Swisstopo_mountains_vector.zip`).
- **How the match was made:** tile coordinates were projected to Swiss LV03 (EPSG:21781). The tile geometry is displaced by about **+90 m east and +217.5 m north (about 235 m)** relative to the source shapefile; this constant shift was measured on polygons that match their source polygon at 99-100% overlap and removed before matching. After the correction every tile polygon lies 91-100% inside a single source polygon (median 99%), and a tile polygon id maps to the same unit at z10, z12 and z14 (no conflicts, 204 ids).
- **Colors are official:** read from the vector swatches of the Swisstopo legend PDF (`GS128-Struct-map-Helvetic-Zone-Legende.pdf`). The same symbol has the same color in the Western, Central and Eastern columns of that legend. `No Data` has no color in the legend and is drawn white.
- Names and ages are from the source attribute table (`DESCRIPT`, `TECTO`), Eastern Switzerland wording; `(limestone)` and `(siliceous limestone)` are translations of `-kalk` formation names.
- The tile marker in the locator grid is magenta `#e6007e`, a color the legend does not use.
- The source layers for fault lines, fold axes and the map border did not make it into the tiles: the tiles contain polygons only.
- Fill / outline are hex colors. **Pattern** = the figure draws a hatch in the pattern color. **Line** = drawn as a line, not a filled area.
- **not official** = no official color exists for this value; the figure uses the neutral fallback color. These are NOT official colors.
- Counts are features in the three displayed tiles (z10 / z12 / z14).

## Rock units  (`terrain`)

| Value | Meaning | Fill | Outline | Style | Source | z10 / z12 / z14 |
|---|---|---|---|---|---|---|
| Sr | Schrattenkalk Fm. (limestone) (Early Cretaceous) | `#7cccbf` | `#4a4a4a` | solid | official Swisstopo legend | 47 / 19 / 6 |
| HK | Helvetic Kieselkalk Fm. (siliceous limestone) (Early Cretaceous) | `#c7c989` | `#4a4a4a` | solid | official Swisstopo legend | 24 / 12 / 3 |
| Pf | Palfris Shale (Early Cretaceous) | `#cbd8d2` | `#4a4a4a` | solid | official Swisstopo legend | 24 / 8 / 2 |
| K2 | Garschella, Seewen, Amden, Wang Fms. (Late Cretaceous) | `#d1e173` | `#4a4a4a` | solid | official Swisstopo legend | 20 / 4 / 2 |
| Db | Drusberg Marl (Early Cretaceous) | `#d3d5b8` | `#4a4a4a` | solid | official Swisstopo legend | 14 / 4 / 2 |
| Oe | Öhrli Limestone (Early Cretaceous) | `#83c994` | `#4a4a4a` | solid | official Swisstopo legend | 12 / 6 / 2 |
| D | Mols, Bommerstein, Raischiben Fms. (Middle Jurassic) | `#8db4ca` | `#4a4a4a` | solid | official Swisstopo legend | 10 / 0 / 0 |
| M | Schilt Fm., Quinten Limestone (Late Jurassic) | `#8dd8f8` | `#4a4a4a` | solid | official Swisstopo legend | 10 / 0 / 0 |
| L | Cardinia, Prodchamm, Spitzmeilen, Sexmoor Fms. (Early Jurassic) | `#c5a8d0` | `#4a4a4a` | solid | official Swisstopo legend | 9 / 0 / 0 |
| Tr | Mels Sandstone, Röti Dolomite, Quarten Fm. (Triassic) | `#fec54e` | `#4a4a4a` | solid | official Swisstopo legend | 7 / 0 / 0 |
| K1 | Early Cretaceous, undivided (Early Cretaceous) | `#9dd29c` | `#4a4a4a` | solid | official Swisstopo legend | 5 / 1 / 0 |
| UH1 | Ultrahelvetic sediments (Triassic–Eocene) | `#b3ddc6` | `#4a4a4a` | solid | official Swisstopo legend | 5 / 1 / 0 |
| T | Bürgen and Stad Fms., North-Helvetic Flysch (Eocene–Early Oligocene) | `#fff57c` | `#4a4a4a` | solid | official Swisstopo legend | 3 / 1 / 0 |
| P | "Verrucano" Group (Permian) | `#fbb781` | `#4a4a4a` | solid | official Swisstopo legend | 3 / 0 / 0 |
| LP2 | Lower Penninic flysch (Late Cretaceous–Eocene) | `#fde0da` | `#4a4a4a` | solid | official Swisstopo legend | 3 / 0 / 0 |
| SF | Subalpine Flysch (Late Cretaceous–Oligocene) | `#fff9ae` | `#4a4a4a` | solid | official Swisstopo legend | 2 / 1 / 0 |
| UMM' | Lower Marine Molasse (subalpine) | `#dfc0ac` | `#4a4a4a` | solid | official Swisstopo legend | 2 / 1 / 0 |
| USM' | Lower Freshwater Molasse (subalpine) | `#fdd2b9` | `#4a4a4a` | solid | official Swisstopo legend | 1 / 1 / 0 |
| No Data | No data (area not classified) | `#ffffff` | `#4a4a4a` | not official |  | 1 / 0 / 0 |
| MP2 | Middle Penninic sediments (Permian–Cretaceous) | `#e0dff0` | `#4a4a4a` | solid | official Swisstopo legend | 1 / 0 / 0 |
| Q | Quaternary valley fill (Pleistocene–Holocene) | `#fff8e6` | `#4a4a4a` | solid | official Swisstopo legend | 1 / 0 / 0 |
