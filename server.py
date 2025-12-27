"""
Flask server for on-the-fly DBSCAN clustering.
"""

import json
import os
import re
from collections import Counter
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import pandas as pd
from sklearn.cluster import DBSCAN

app = Flask(__name__, static_folder='outputs')
CORS(app)

DATA = None


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

    DATA = {
        'df': df,
        'day_df': df[df['period'] == 'Day'],
        'night_df': df[df['period'] == 'Night'],
        'center_lat': df['latitude'].mean(),
        'center_lon': df['longitude'].mean()
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
