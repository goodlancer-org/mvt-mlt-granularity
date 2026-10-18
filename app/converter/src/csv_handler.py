"""Convert country-level CSV time series data to GeoPackage with country geometries."""

import csv
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path


def _get_world_countries_geojson():
    """
    Return a minimal world countries GeoJSON for joining CSV data.
    Uses country ISO 3166-1 alpha-3 codes.
    
    This is a fallback that creates a simple feature collection.
    For production, download from: https://naciscdn.org/naturalearth/110m/cultural/
    """
    # Minimal world countries GeoJSON (centroids + basic polygons)
    # In production, embed the full Natural Earth dataset
    return {
        "type": "FeatureCollection",
        "features": []  # Will be populated from external source or Natural Earth
    }


def merge_csv_files(csv_paths):
    """
    Merge multiple CSV files by ISO code + country.
    Handles both comma-separated and tab-separated formats.
    
    Returns a dict: { iso_code: { country, year_data, ... } }
    """
    data = {}
    
    for csv_path in csv_paths:
        csv_path = Path(csv_path)
        try:
            # Detect delimiter
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                sample = f.read(512)
            delimiter = '\t' if '\t' in sample else ','
            
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                if not reader.fieldnames:
                    continue
                    
                for row in reader:
                    iso = row.get('iso', '').strip().upper()
                    if not iso or len(iso) != 3:  # ISO 3 letter code
                        continue
                    
                    if iso not in data:
                        data[iso] = {
                            'country': row.get('country', iso),
                            'iso': iso
                        }
                    
                    # Merge all numeric columns (skip iso/country)
                    for key, val in row.items():
                        key_lower = key.lower()
                        if key_lower not in ('iso', 'country') and val and val.strip():
                            try:
                                # Try to convert to float for numeric columns
                                data[iso][key] = float(val)
                            except (ValueError, TypeError):
                                # Keep as string if not numeric
                                data[iso][key] = val
        except Exception as e:
            print(f"  Warning: Error reading CSV {csv_path.name}: {e}")
            continue
    
    return data


def csv_to_gpkg(source_path, output_path, progress_callback=None):
    """
    Convert country-level CSV data to GeoPackage with world country boundaries.
    
    Process:
    1. Extract CSV files from archive (if .zip)
    2. Merge CSV data by ISO code
    3. Create GeoJSON with country centroids + CSV attributes
    4. Convert GeoJSON to GeoPackage via ogr2ogr
    
    Args:
        source_path: Path to CSV file or .zip archive
        output_path: Output GeoPackage path
        progress_callback: Optional progress reporting function
    """
    source_path = Path(source_path)
    output_path = Path(output_path)
    
    def log_progress(msg):
        if progress_callback:
            progress_callback("csv_convert", msg)
        print(f"    {msg}")
    
    log_progress("Extracting CSV files...")
    csv_files = []
    
    # Step 1: Extract/collect CSV files
    if source_path.suffix.lower() == '.zip':
        try:
            with zipfile.ZipFile(source_path) as zf:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmpdir_path = Path(tmpdir)
                    for name in zf.namelist():
                        if name.endswith(('.csv', '.tsv')):
                            zf.extract(name, tmpdir)
                            extracted = tmpdir_path / name
                            if extracted.exists():
                                csv_files.append(extracted)
                    
                    if not csv_files:
                        raise ValueError("No CSV/TSV files found in ZIP archive")
                    
                    log_progress(f"Found {len(csv_files)} CSV files in archive")
                    merged = merge_csv_files(csv_files)
        except zipfile.BadZipFile as e:
            raise ValueError(f"Invalid ZIP file: {e}")
    else:
        csv_files = [source_path]
        merged = merge_csv_files(csv_files)
    
    if not merged:
        raise ValueError("No valid country data found in CSV files")
    
    log_progress(f"Merged data for {len(merged)} countries")
    
    # Step 2: Create GeoJSON with country centroids + CSV data
    # Using approximate country centroids (lat/lon)
    country_centroids = _get_country_centroids()
    
    output_geojson = {
        "type": "FeatureCollection",
        "features": []
    }
    
    for iso, csv_data in merged.items():
        if iso not in country_centroids:
            continue
        
        lon, lat = country_centroids[iso]
        
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": csv_data
        }
        output_geojson["features"].append(feature)
    
    log_progress(f"Created GeoJSON with {len(output_geojson['features'])} countries")
    
    # Step 3: Convert GeoJSON to GeoPackage via ogr2ogr
    log_progress("Converting to GeoPackage...")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False) as f:
        json.dump(output_geojson, f)
        temp_geojson = Path(f.name)
    
    try:
        result = subprocess.run(
            [
                'ogr2ogr',
                '-f', 'GPKG',
                '-nln', 'countries',  # Layer name
                str(output_path),
                str(temp_geojson)
            ],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"ogr2ogr failed: {result.stderr}")
        
        file_size = output_path.stat().st_size if output_path.exists() else 0
        log_progress(f"GeoPackage created: {file_size / (1024*1024):.2f} MB")
        
    finally:
        temp_geojson.unlink(missing_ok=True)


def _get_country_centroids():
    """
    Return a dict of ISO 3-letter codes to (lon, lat) centroids.
    Approximate values for display purposes.
    """
    return {
        'AFG': (67.71, 33.94),
        'ALB': (20.17, 41.15),
        'DZA': (1.66, 28.03),
        'AND': (1.60, 42.55),
        'AGO': (17.87, -11.20),
        'AIA': (-63.07, 18.22),
        'ATA': (0.00, -90.00),
        'ATG': (-61.78, 17.07),
        'ARG': (-63.62, -38.42),
        'ARM': (45.04, 40.07),
        'ABW': (-69.97, 12.18),
        'AUS': (133.78, -25.27),
        'AUT': (14.55, 47.52),
        'AZE': (47.58, 40.14),
        'BHS': (-76.80, 24.21),
        'BHR': (50.55, 26.13),
        'BGD': (90.36, 23.68),
        'BRB': (-59.54, 13.19),
        'BLR': (27.95, 53.71),
        'BEL': (4.48, 50.50),
        'BLZ': (-88.75, 17.19),
        'BEN': (2.35, 9.31),
        'BMU': (-64.78, 32.29),
        'BTN': (90.43, 27.51),
        'BOL': (-63.59, -16.29),
        'BIH': (17.68, 43.92),
        'BWA': (22.33, -22.33),
        'BRA': (-51.93, -14.24),
        'VGB': (-64.60, 18.42),
        'BRN': (114.73, 4.54),
        'BGR': (25.49, 42.73),
        'BFA': (-1.56, 12.24),
        'BDI': (29.92, -3.37),
        'KHM': (104.99, 12.57),
        'CMR': (12.35, 3.85),
        'CAN': (-106.35, 56.13),
        'CPV': (-23.64, 16.04),
        'CYM': (-81.36, 19.52),
        'CAF': (21.76, 6.61),
        'TCD': (19.00, 15.47),
        'CHL': (-71.54, -35.68),
        'CHN': (104.20, 35.86),
        'HKG': (114.11, 22.40),
        'MAC': (113.54, 22.20),
        'TWN': (120.96, 23.70),
        'COL': (-74.30, 4.57),
        'COM': (43.33, -11.88),
        'COG': (21.76, -4.04),
        'COK': (-159.78, -21.24),
        'CRI': (-83.75, 9.75),
        'CIV': (-5.55, 7.54),
        'HRV': (15.20, 45.10),
        'CUB': (-77.79, 21.52),
        'CYP': (33.43, 34.92),
        'CZE': (15.47, 49.82),
        'DNK': (9.50, 56.26),
        'DJI': (42.59, 11.86),
        'DMA': (-61.38, 15.41),
        'DOM': (-70.16, 18.74),
        'ECU': (-78.18, -1.83),
        'EGY': (30.80, 26.82),
        'SLV': (-88.90, 13.79),
        'GNQ': (10.27, 1.65),
        'ERI': (39.15, 15.18),
        'EST': (25.75, 58.60),
        'ETH': (40.49, 9.15),
        'FLK': (-59.52, -51.75),
        'FRO': (-6.92, 62.01),
        'FJI': (177.00, -18.00),
        'FIN': (25.75, 61.92),
        'FRA': (2.21, 46.57),
        'GUF': (-53.13, 3.93),
        'PYF': (-149.41, -17.68),
        'GAB': (13.44, -1.87),
        'GMB': (-15.31, 13.45),
        'GEO': (43.36, 42.32),
        'DEU': (10.45, 51.17),
        'GHA': (-2.04, 7.37),
        'GIB': (-5.36, 36.14),
        'GRC': (21.82, 39.07),
        'GRL': (-42.60, 72.00),
        'GRD': (-61.60, 12.11),
        'GLP': (-61.55, 16.23),
        'GUM': (144.80, 13.44),
        'GTM': (-90.50, 15.78),
        'GGY': (-2.50, 49.46),
        'GIN': (-10.27, 9.95),
        'GNB': (-15.18, 11.80),
        'GUY': (-58.93, 4.86),
        'HTI': (-72.29, 18.97),
        'HND': (-86.24, 15.20),
        'HUN': (19.50, 47.16),
        'ISL': (-19.02, 64.96),
        'IND': (78.30, 20.59),
        'IDN': (113.92, -2.17),
        'IRN': (53.69, 32.43),
        'IRQ': (44.36, 33.31),
        'IRL': (-8.24, 53.41),
        'IMN': (-4.55, 54.24),
        'ISR': (35.13, 31.05),
        'ITA': (12.57, 41.87),
        'JAM': (-77.30, 18.11),
        'JPN': (138.25, 36.20),
        'JEY': (-2.12, 49.18),
        'JOR': (35.93, 30.59),
        'KAZ': (66.92, 48.02),
        'KEN': (37.67, -0.02),
        'KIR': (-157.44, 1.35),
        'PRK': (127.11, 40.34),
        'KOR': (127.77, 37.27),
        'KWT': (47.48, 29.31),
        'KGZ': (74.87, 41.20),
        'LAO': (104.87, 19.86),
        'LVA': (24.60, 56.88),
        'LBN': (35.86, 33.85),
        'LSO': (28.61, -29.61),
        'LBR': (-9.43, 6.43),
        'LBY': (17.20, 26.34),
        'LIE': (9.56, 47.27),
        'LTU': (23.88, 55.17),
        'LUX': (6.13, 49.82),
        'MKD': (21.75, 41.61),
        'MDG': (46.87, -18.67),
        'MWI': (34.30, -13.25),
        'MYS': (101.69, 4.21),
        'MDV': (73.51, 4.17),
        'MLI': (-4.00, 17.57),
        'MLT': (14.58, 35.94),
        'MHL': (171.19, 7.11),
        'MTQ': (-61.02, 14.64),
        'MRT': (-11.55, 21.01),
        'MUS': (57.55, -20.35),
        'MYT': (45.17, -12.83),
        'MEX': (-102.55, 23.63),
        'FSM': (158.19, 7.43),
        'MDA': (28.37, 47.41),
        'MCO': (7.41, 43.74),
        'MNG': (103.85, 46.86),
        'MNE': (19.37, 42.71),
        'MAR': (-5.00, 31.79),
        'MOZ': (35.35, -18.66),
        'MMR': (95.96, 21.91),
        'NAM': (17.08, -22.96),
        'NRU': (166.93, -0.52),
        'NPL': (84.12, 28.39),
        'NLD': (5.29, 52.13),
        'ANT': (-69.00, 12.15),
        'NCL': (165.62, -21.24),
        'NZL': (174.89, -40.90),
        'NIC': (-85.21, 12.87),
        'NER': (2.13, 17.61),
        'NGA': (8.68, 9.08),
        'NIU': (-169.87, -19.05),
        'NFK': (167.95, -29.04),
        'MNP': (145.59, 15.10),
        'NOR': (8.47, 60.47),
        'OMN': (55.92, 21.51),
        'PAK': (69.35, 30.19),
        'PLW': (134.58, 7.35),
        'PAN': (-80.44, 8.68),
        'PNG': (147.18, -6.32),
        'PRY': (-56.17, -23.44),
        'PER': (-75.73, -9.19),
        'PHL': (121.77, 12.88),
        'PCN': (-124.78, -24.70),
        'POL': (19.15, 51.92),
        'PRT': (-8.22, 39.40),
        'PRI': (-66.59, 18.22),
        'QAT': (51.20, 25.35),
        'ROU': (24.97, 45.94),
        'RUS': (105.32, 61.52),
        'RWA': (29.75, -1.94),
        'KNA': (-62.78, 17.36),
        'LCA': (-61.06, 13.91),
        'VCT': (-61.27, 12.98),
        'WSM': (-172.10, -13.76),
        'SMR': (12.46, 43.94),
        'STP': (7.42, 0.81),
        'SAU': (45.21, 23.89),
        'SEN': (-14.50, 14.50),
        'SRB': (21.01, 44.02),
        'SYC': (55.49, -4.68),
        'SLE': (-11.78, 8.46),
        'SGP': (103.82, 1.35),
        'SVK': (19.70, 48.67),
        'SVN': (14.55, 46.15),
        'SLB': (160.20, -9.65),
        'SOM': (46.20, 5.15),
        'ZAF': (22.94, -30.56),
        'SSD': (30.81, 6.88),
        'ESP': (-3.74, 40.46),
        'LKA': (80.77, 7.87),
        'SDN': (30.82, 12.86),
        'SUR': (-56.03, 3.92),
        'SWZ': (31.47, -26.52),
        'SWE': (18.64, 60.13),
        'CHE': (8.23, 46.82),
        'SYR': (34.80, 34.93),
        'TWN': (120.96, 23.70),
        'TJK': (71.28, 38.86),
        'TZA': (34.89, -6.37),
        'THA': (100.99, 15.87),
        'TLS': (124.74, -8.87),
        'TGO': (1.17, 7.37),
        'TKL': (-172.00, -9.35),
        'TON': (-175.20, -21.18),
        'TTO': (-61.37, 10.69),
        'TUN': (9.54, 33.89),
        'TUR': (35.24, 38.96),
        'TKM': (59.56, 38.97),
        'TCA': (-71.58, 21.94),
        'TUV': (179.20, -8.52),
        'UGA': (32.29, 1.37),
        'UKR': (31.17, 48.38),
        'ARE': (53.85, 23.42),
        'GBR': (-3.44, 55.38),
        'USA': (-95.71, 37.09),
        'URY': (-56.17, -32.52),
        'UZB': (64.59, 41.38),
        'VUT': (167.84, -17.73),
        'VAT': (12.45, 41.90),
        'VEN': (-66.59, 6.42),
        'VNM': (105.87, 20.84),
        'VGB': (-64.60, 18.42),
        'VIR': (-64.90, 18.34),
        'WLF': (-176.17, -13.28),
        'ESH': (-13.20, 24.22),
        'YEM': (48.52, 15.55),
        'ZMB': (28.29, -13.13),
        'ZWE': (29.61, -19.02),
    }
