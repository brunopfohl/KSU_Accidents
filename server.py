"""
Flask server for traffic accident hotspot analysis.
Supports both DBSCAN clustering and Getis-Ord Gi* statistical hotspot detection.
"""

import json
import re
import warnings
from collections import Counter
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
import geopandas as gpd
from shapely.geometry import Point, box
from libpysal.weights import KNN
from esda.getisord import G_Local
from scipy import stats

warnings.filterwarnings('ignore')

app = Flask(__name__, static_folder='outputs')
CORS(app)

DATA = None
GRID_CACHE = {}


def parse_damage(value):
    """Parse hmotna_skoda to integer."""
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        # Extract numbers from string like "35 000 Kč"
        numbers = re.findall(r'\d+', value.replace(' ', ''))
        if numbers:
            return int(''.join(numbers))
    return 0


def load_data():
    """Load and preprocess data once at startup."""
    global DATA
    if DATA is not None:
        return DATA

    print("Loading data...")
    with open('data/nehody_202001-202512.geojson', 'r', encoding='utf-8') as f:
        geojson = json.load(f)

    records = []
    for feature in geojson['features']:
        props = feature['properties']
        coords = feature['geometry']['coordinates']
        records.append({
            'datum': props.get('datum'),
            'druh': props.get('druh'),
            'pricina': props.get('pricina'),
            'usmrceno': props.get('usmrceno', 0),
            'tezce_zraneno': props.get('tezce_zraneno', 0),
            'lehce_zraneno': props.get('lehce_zraneno', 0),
            'hmotna_skoda_raw': props.get('hmotna_skoda'),
            'longitude': coords[0],
            'latitude': coords[1]
        })

    df = pd.DataFrame(records)
    df['hmotna_skoda'] = df['hmotna_skoda_raw'].apply(parse_damage)
    df['datetime'] = pd.to_datetime(df['datum'], utc=True)
    df['datetime'] = df['datetime'].dt.tz_convert('Europe/Prague')
    df['hour'] = df['datetime'].dt.hour
    df['period'] = df['hour'].apply(lambda h: 'Day' if 6 <= h <= 18 else 'Night')
    df['severity_score'] = df['usmrceno'] * 100 + df['tezce_zraneno'] * 10 + df['lehce_zraneno']

    # Create GeoDataFrame for spatial analysis
    geometry = [Point(xy) for xy in zip(df['longitude'], df['latitude'])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]

    DATA = {
        'df': df,
        'gdf': gdf,
        'day_df': df[df['period'] == 'Day'],
        'night_df': df[df['period'] == 'Night'],
        'day_gdf': gdf[gdf['period'] == 'Day'].copy(),
        'night_gdf': gdf[gdf['period'] == 'Night'].copy(),
        'center_lat': df['latitude'].mean(),
        'center_lon': df['longitude'].mean(),
        'bounds': bounds
    }
    print(f"Loaded {len(df)} records (Day: {len(DATA['day_df'])}, Night: {len(DATA['night_df'])})")
    return DATA


def compute_clusters(df, eps_km, min_samples):
    """Run DBSCAN and return cluster profiles."""
    if len(df) < min_samples:
        return []

    eps_deg = eps_km / 111.0
    coords = df[['latitude', 'longitude']].values

    dbscan = DBSCAN(eps=eps_deg, min_samples=min_samples, metric='euclidean')
    labels = dbscan.fit_predict(coords)

    df = df.copy()
    df['cluster'] = labels

    clusters = []
    for cluster_id in set(labels):
        if cluster_id == -1:
            continue

        cluster_data = df[df['cluster'] == cluster_id]
        causes = cluster_data['pricina'].dropna()
        dominant_cause = Counter(causes).most_common(1)[0][0] if len(causes) > 0 else 'Unknown'

        clusters.append({
            'lat': float(cluster_data['latitude'].mean()),
            'lon': float(cluster_data['longitude'].mean()),
            'count': int(len(cluster_data)),
            'cause': dominant_cause,
            'fatalities': int(cluster_data['usmrceno'].sum()),
            'serious': int(cluster_data['tezce_zraneno'].sum()),
            'minor': int(cluster_data['lehce_zraneno'].sum()),
            'damage': int(cluster_data['hmotna_skoda'].sum())
        })

    clusters.sort(key=lambda x: x['count'], reverse=True)
    return clusters


def filter_dataframe(df, filters):
    """Apply filters to dataframe."""
    result = df.copy()

    # Severity filter
    severity = filters.get('severity', 'all')
    if severity == 'fatal':
        result = result[result['usmrceno'] > 0]
    elif severity == 'serious':
        result = result[(result['usmrceno'] > 0) | (result['tezce_zraneno'] > 0)]
    elif severity == 'injury':
        result = result[(result['usmrceno'] > 0) | (result['tezce_zraneno'] > 0) | (result['lehce_zraneno'] > 0)]

    # Min damage filter
    if filters.get('min_damage', 0) > 0:
        result = result[result['hmotna_skoda'] >= filters['min_damage']]

    # Type filter (druh)
    types = filters.get('types', [])
    if types:
        result = result[result['druh'].isin(types)]

    return result


# =============================================================================
# Getis-Ord Gi* Functions
# =============================================================================

def create_grid(bounds, cell_size_m=200):
    """Create a grid of cells covering the study area (vectorized)."""
    minx, miny, maxx, maxy = bounds
    cell_size_deg = cell_size_m / 111000  # 1 degree ≈ 111km

    # Create coordinate arrays
    x_edges = np.arange(minx, maxx + cell_size_deg, cell_size_deg)
    y_edges = np.arange(miny, maxy + cell_size_deg, cell_size_deg)
    num_cols = len(x_edges) - 1
    num_rows = len(y_edges) - 1

    # Create cell centers using meshgrid (vectorized)
    x_centers = x_edges[:-1] + cell_size_deg / 2
    y_centers = y_edges[:-1] + cell_size_deg / 2
    xx, yy = np.meshgrid(x_centers, y_centers)

    # Flatten to 1D arrays
    center_lons = xx.flatten()
    center_lats = yy.flatten()
    cell_ids = np.arange(len(center_lons))

    # Create point geometries for KNN (faster than boxes, works for spatial weights)
    geometries = gpd.points_from_xy(center_lons, center_lats)

    return gpd.GeoDataFrame({
        'cell_id': cell_ids,
        'center_lon': center_lons,
        'center_lat': center_lats,
        'geometry': geometries
    }, crs="EPSG:4326")


def aggregate_to_grid(gdf, grid, bounds, cell_size_m):
    """Count accidents per grid cell using fast vectorized calculation."""
    grid = grid.copy()

    # Initialize columns
    grid['count'] = 0
    grid['usmrceno'] = 0
    grid['tezce_zraneno'] = 0
    grid['lehce_zraneno'] = 0
    grid['hmotna_skoda'] = 0
    grid['severity_score'] = 0
    grid['dominant_cause'] = None

    if len(gdf) == 0:
        return grid

    # Calculate cell size and grid dimensions
    minx, miny, maxx, maxy = bounds
    cell_size_deg = cell_size_m / 111000
    num_cols = int(np.ceil((maxx - minx) / cell_size_deg))

    # Fast vectorized cell assignment (no geometry operations)
    lons = gdf['longitude'].values
    lats = gdf['latitude'].values
    col_idx = ((lons - minx) / cell_size_deg).astype(int)
    row_idx = ((lats - miny) / cell_size_deg).astype(int)
    cell_ids = row_idx * num_cols + col_idx

    # Add cell_id to gdf for groupby
    gdf = gdf.copy()
    gdf['cell_id'] = cell_ids

    # Aggregate
    agg = gdf.groupby('cell_id').agg({
        'longitude': 'count',  # count rows
        'usmrceno': 'sum',
        'tezce_zraneno': 'sum',
        'lehce_zraneno': 'sum',
        'hmotna_skoda': 'sum',
        'severity_score': 'sum',
        'pricina': lambda x: Counter(x.dropna()).most_common(1)[0][0] if len(x.dropna()) > 0 else None
    }).rename(columns={'longitude': 'count', 'pricina': 'dominant_cause'})

    # Update grid with aggregated values
    for col in ['count', 'usmrceno', 'tezce_zraneno', 'lehce_zraneno', 'hmotna_skoda', 'severity_score']:
        grid.loc[agg.index, col] = agg[col].astype(int)
    grid.loc[agg.index, 'dominant_cause'] = agg['dominant_cause']

    return grid


def compute_getis_ord(grid_with_counts, value_column='count'):
    """Compute Getis-Ord Gi* statistics for the grid (optimized)."""
    # Initialize defaults
    grid_with_counts['z_score'] = 0.0
    grid_with_counts['p_value'] = 1.0
    grid_with_counts['significant'] = False

    # Only compute on cells with accidents
    mask = grid_with_counts['count'] > 0
    non_empty = grid_with_counts[mask].copy()

    if len(non_empty) < 10:
        return grid_with_counts

    try:
        values = non_empty[value_column].values
        k = min(5, len(non_empty) - 1)
        w = KNN.from_dataframe(non_empty, k=k)
        w.transform = 'r'

        # Analytical p-values (permutations=0) - fast and academically standard
        gi = G_Local(values, w, star=True, permutations=0)

        # Directly assign to masked rows
        grid_with_counts.loc[mask, 'z_score'] = gi.Zs
        grid_with_counts.loc[mask, 'p_value'] = gi.p_norm  # analytical p-value
        grid_with_counts.loc[mask, 'significant'] = gi.p_norm < 0.05

    except Exception as e:
        print(f"Getis-Ord error: {e}")

    return grid_with_counts


def compare_day_night(day_grid, night_grid, total_day, total_night):
    """Compare day vs night using binomial test. Find statistically significant anomalies."""
    if total_day + total_night == 0:
        return []

    expected_night_ratio = total_night / (total_day + total_night)
    results = []

    for idx in day_grid.index:
        day_count = int(day_grid.loc[idx, 'count'])
        night_count = int(night_grid.loc[idx, 'count'])
        total = day_count + night_count

        if total < 5:
            continue

        observed_night_ratio = night_count / total
        p_value = stats.binomtest(night_count, total, expected_night_ratio).pvalue

        if p_value < 0.05:
            results.append({
                'cell_id': int(idx),
                'lat': float(day_grid.loc[idx, 'center_lat']),
                'lon': float(day_grid.loc[idx, 'center_lon']),
                'day_count': day_count,
                'night_count': night_count,
                'total': total,
                'observed_night_ratio': round(observed_night_ratio, 3),
                'expected_night_ratio': round(expected_night_ratio, 3),
                'p_value': round(p_value, 4),
                'type': 'night_anomaly' if observed_night_ratio > expected_night_ratio else 'day_anomaly',
                'dominant_cause_day': day_grid.loc[idx, 'dominant_cause'],
                'dominant_cause_night': night_grid.loc[idx, 'dominant_cause']
            })

    return sorted(results, key=lambda x: x['p_value'])


def filter_geodataframe(gdf, filters):
    """Apply filters to geodataframe."""
    result = gdf.copy()

    severity = filters.get('severity', 'all')
    if severity == 'fatal':
        result = result[result['usmrceno'] > 0]
    elif severity == 'serious':
        result = result[(result['usmrceno'] > 0) | (result['tezce_zraneno'] > 0)]
    elif severity == 'injury':
        result = result[(result['usmrceno'] > 0) | (result['tezce_zraneno'] > 0) | (result['lehce_zraneno'] > 0)]

    if filters.get('min_damage', 0) > 0:
        result = result[result['hmotna_skoda'] >= filters['min_damage']]

    types = filters.get('types', [])
    if types:
        result = result[result['druh'].isin(types)]

    return result


@app.route('/')
def index():
    return send_from_directory('outputs', 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('outputs', filename)


def get_filters_from_request():
    """Extract filters from request args."""
    types_param = request.args.get('types', '')
    types = [t.strip() for t in types_param.split('|') if t.strip()] if types_param else []

    return {
        'severity': request.args.get('severity', 'all'),
        'min_damage': int(request.args.get('min_damage', 0)),
        'types': types
    }


@app.route('/api/cluster')
def api_cluster():
    """Compute clusters on the fly with filters."""
    data = load_data()

    eps_km = float(request.args.get('eps', 0.2))
    min_samples = int(request.args.get('min_samples', 3))
    filters = get_filters_from_request()

    eps_km = max(0.05, min(2.0, eps_km))
    min_samples = max(2, min(10000, min_samples))

    day_df = filter_dataframe(data['day_df'], filters)
    night_df = filter_dataframe(data['night_df'], filters)

    day_clusters = compute_clusters(day_df, eps_km, min_samples)
    night_clusters = compute_clusters(night_df, eps_km, min_samples)

    return jsonify({
        'eps': eps_km,
        'min_samples': min_samples,
        'day': day_clusters,
        'night': night_clusters,
        'day_count': len(day_clusters),
        'night_count': len(night_clusters),
        'day_points': len(day_df),
        'night_points': len(night_df)
    })


@app.route('/api/hotspots')
def api_hotspots():
    """Compute Getis-Ord Gi* hotspots with statistical significance."""
    data = load_data()

    cell_size = int(request.args.get('cell_size', 300))
    cell_size = max(100, min(1000, cell_size))
    filters = get_filters_from_request()

    # Filter data
    day_gdf = filter_geodataframe(data['day_gdf'], filters)
    night_gdf = filter_geodataframe(data['night_gdf'], filters)

    # Create or get cached grid
    cache_key = f"{cell_size}"
    if cache_key not in GRID_CACHE:
        GRID_CACHE[cache_key] = create_grid(data['bounds'], cell_size)
    grid = GRID_CACHE[cache_key].copy()

    # Aggregate accidents to grid
    day_grid = aggregate_to_grid(day_gdf, grid.copy(), data['bounds'], cell_size)
    night_grid = aggregate_to_grid(night_gdf, grid.copy(), data['bounds'], cell_size)

    # Compute Getis-Ord Gi*
    day_grid = compute_getis_ord(day_grid, 'count')
    night_grid = compute_getis_ord(night_grid, 'count')

    # Extract significant hotspots (z > 0 means hot spot, z < 0 means cold spot)
    def extract_hotspots(grid_result, period):
        hotspots = []
        significant = grid_result[(grid_result['significant']) & (grid_result['z_score'] > 0)]
        for _, row in significant.iterrows():
            hotspots.append({
                'lat': float(row['center_lat']),
                'lon': float(row['center_lon']),
                'count': int(row['count']),
                'z_score': round(float(row['z_score']), 2),
                'p_value': round(float(row['p_value']), 4),
                'fatalities': int(row['usmrceno']),
                'serious': int(row['tezce_zraneno']),
                'minor': int(row['lehce_zraneno']),
                'damage': int(row['hmotna_skoda']),
                'cause': row['dominant_cause'],
                'period': period
            })
        return sorted(hotspots, key=lambda x: x['z_score'], reverse=True)

    day_hotspots = extract_hotspots(day_grid, 'Day')
    night_hotspots = extract_hotspots(night_grid, 'Night')

    # Compare day vs night - find anomalies
    anomalies = compare_day_night(day_grid, night_grid, len(day_gdf), len(night_gdf))

    return jsonify({
        'cell_size': cell_size,
        'day_hotspots': day_hotspots,
        'night_hotspots': night_hotspots,
        'day_hotspot_count': len(day_hotspots),
        'night_hotspot_count': len(night_hotspots),
        'day_accidents': len(day_gdf),
        'night_accidents': len(night_gdf),
        'anomalies': anomalies[:20],
        'total_anomalies': len(anomalies),
        'night_anomalies': len([a for a in anomalies if a['type'] == 'night_anomaly']),
        'day_anomalies': len([a for a in anomalies if a['type'] == 'day_anomaly'])
    })


@app.route('/api/accidents')
def api_accidents():
    """Get filtered accidents."""
    data = load_data()
    filters = get_filters_from_request()

    day_df = filter_dataframe(data['day_df'], filters)
    night_df = filter_dataframe(data['night_df'], filters)

    def to_features(df, period):
        features = []
        for _, row in df.iterrows():
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [row['longitude'], row['latitude']]},
                'properties': {
                    'period': period,
                    'druh': row['druh'],
                    'pricina': row['pricina'],
                    'datetime': row['datetime'].isoformat() if pd.notna(row['datetime']) else None,
                    'hour': int(row['hour']),
                    'usmrceno': int(row['usmrceno']),
                    'tezce_zraneno': int(row['tezce_zraneno']),
                    'lehce_zraneno': int(row['lehce_zraneno']),
                    'hmotna_skoda': int(row['hmotna_skoda'])
                }
            })
        return features

    return jsonify({
        'day': {'type': 'FeatureCollection', 'features': to_features(day_df, 'Day')},
        'night': {'type': 'FeatureCollection', 'features': to_features(night_df, 'Night')},
        'day_count': len(day_df),
        'night_count': len(night_df)
    })


@app.route('/api/stats')
def api_stats():
    """Return basic stats."""
    data = load_data()

    # Get unique types with counts
    type_counts = data['df']['druh'].value_counts().to_dict()
    types = [{'name': k, 'count': v} for k, v in type_counts.items() if pd.notna(k)]
    types.sort(key=lambda x: x['count'], reverse=True)

    return jsonify({
        'total': len(data['df']),
        'day': len(data['day_df']),
        'night': len(data['night_df']),
        'center_lat': data['center_lat'],
        'center_lon': data['center_lon'],
        'max_damage': int(data['df']['hmotna_skoda'].max()),
        'total_fatalities': int(data['df']['usmrceno'].sum()),
        'total_serious': int(data['df']['tezce_zraneno'].sum()),
        'total_minor': int(data['df']['lehce_zraneno'].sum()),
        'types': types
    })


if __name__ == '__main__':
    load_data()
    print("\nServer running at http://localhost:5000")
    app.run(port=5000, debug=False)
