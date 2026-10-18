# Sources, attribution and reproducibility

The corpus contains five vector sources. Original files, normalized GeoPackages,
PMTiles archives and local credentials are excluded from the code repository.

| Source | Attribution and source terms | Entry point |
|---|---|---|
| Natural Earth | Made with Natural Earth; public domain | [Terms](https://www.naturalearthdata.com/about/terms-of-use/) |
| USFWS NWI | U.S. Fish and Wildlife Service, National Wetlands Inventory | [Data and metadata](https://www.fws.gov/program/national-wetlands-inventory/download-state-wetlands-data) |
| swisstopo | Source: swisstopo; source reference required | [Official terms](https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices) |
| OpenStreetMap | © OpenStreetMap contributors; ODbL | [Copyright and licence](https://www.openstreetmap.org/copyright) |
| PDOK BGT | Source: PDOK / BGT; consult the specific product metadata and conditions | [BGT](https://www.pdok.nl/introductie/-/article/basisregistratie-grootschalige-topografie-bgt-) |

These links identify providers and terms, **not the exact bytes used in the article**.
`analysis/sources.json` records the SHA-256 of each measured input from the original
measurement manifests. Input sizes were recovered from the source inventory, and version/date labels
from Table 1 of the article (including the approximate PDOK snapshot month).
Exact acquisition URLs and retrieval dates were not retained; those values remain
explicitly `null`. Version labels do not prove an exact acquisition location. A filename date is not acquisition
evidence. In particular, historical Geofabrik extracts and custom PDOK/swisstopo
selections may no longer be available. Exact source regeneration therefore depends
on recovering matching original files. Do not replace them silently with latest.

```sh
python manage.py download-sources --verify-only
# To enable downloading, fill url with a verified HTTPS location in sources.json.
python manage.py download-sources
```

The downloader verifies SHA-256 and, when known, byte length before replacing a
destination. Existing local files are verified too. An absent URL produces an
actionable error. `retrieved_at` and `version` should be completed only from evidence.

`validation_examples.json`, `attribute_type_profiles.before_examples_json`,
`field_values`, `property_values`, semantic inventories and map images can expose
original values or geometry. Source terms still apply to extracted material.
Aggregate byte/count statistics should be distinguished from those extracts when
preparing a dataset licence. Project code is distributed under the
[MIT License](../LICENSE). This software licence does not relicense source datasets
or third-party assets, which retain their upstream terms.
