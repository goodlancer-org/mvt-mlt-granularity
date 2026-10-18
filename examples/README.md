# A first map without downloads

`points.geojson` is a synthetic three-point EPSG:4326 source with invented names
and populations; it contains no extracted corpus values. Upload it in the web UI
after `python manage.py up`, normalize it, then generate and preview the tile pairs.
Choose a small maximum zoom for the first run. The five-source article analysis
uses its own registry and does not automatically include this example.

The integration tests generate more demanding temporary fixtures: geometries,
typed attributes, duplicate payload addresses, corrupt frames, missing pairs and
empty tables. Run `python manage.py test` to exercise those cases.
