"""
Spatio-Temporal Accident Analysis for Liberec
Analyzes traffic accident clusters distinguishing between Daytime and Nighttime hotspots.
Uses DBSCAN for density-based clustering to find natural hotspots.
"""

import json
import os
from collections import Counter

import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN


def load_geojson(filepath: str) -> pd.DataFrame:
    """Load GeoJSON file and convert to DataFrame."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    records = []
    for feature in data['features']:
        props = feature['properties']
        coords = feature['geometry']['coordinates']
        record = {
            'datum': props.get('datum'),
            'druh': props.get('druh'),
            'pricina': props.get('pricina'),
            'usmrceno': props.get('usmrceno', 0),
            'tezce_zraneno': props.get('tezce_zraneno', 0),
            'lehce_zraneno': props.get('lehce_zraneno', 0),
            'hmotna_skoda': props.get('hmotna_skoda'),
            'longitude': coords[0],
            'latitude': coords[1]
        }
        records.append(record)

    return pd.DataFrame(records)


def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    """Extract hour from datum and create day/night period column."""
    df['datetime'] = pd.to_datetime(df['datum'], utc=True)
    df['datetime'] = df['datetime'].dt.tz_convert('Europe/Prague')
    df['hour'] = df['datetime'].dt.hour
    df['period'] = df['hour'].apply(lambda h: 'Day' if 6 <= h <= 18 else 'Night')
    return df


def perform_clustering_multi_eps(df: pd.DataFrame, eps_values: list, min_samples: int = 3) -> dict:
    """
    Perform DBSCAN clustering at multiple eps values.

    Returns dict with results for each eps value.
    """
    all_results = {}

    for eps_km in eps_values:
        eps_deg = eps_km / 111.0
        results = {}

        for period in ['Day', 'Night']:
            period_df = df[df['period'] == period].copy()

            if len(period_df) < min_samples:
                results[period] = {'profiles': [], 'n_clusters': 0}
                continue

            coords = period_df[['latitude', 'longitude']].values
            dbscan = DBSCAN(eps=eps_deg, min_samples=min_samples, metric='euclidean')
            period_df['cluster'] = dbscan.fit_predict(coords)

            unique_clusters = [c for c in period_df['cluster'].unique() if c != -1]

            cluster_profiles = []
            for cluster_id in unique_clusters:
                cluster_data = period_df[period_df['cluster'] == cluster_id]

                centroid_lat = cluster_data['latitude'].mean()
                centroid_lon = cluster_data['longitude'].mean()

                causes = cluster_data['pricina'].dropna()
                dominant_cause = Counter(causes).most_common(1)[0][0] if len(causes) > 0 else 'Unknown'

                severity = (
                    cluster_data['usmrceno'].sum() * 10 +
                    cluster_data['tezce_zraneno'].sum() * 5 +
                    cluster_data['lehce_zraneno'].sum()
                )

                cluster_profiles.append({
                    'cluster_id': int(cluster_id),
                    'centroid_lat': float(centroid_lat),
                    'centroid_lon': float(centroid_lon),
                    'dominant_cause': dominant_cause,
                    'accident_count': int(len(cluster_data)),
                    'severity_score': int(severity),
                    'fatalities': int(cluster_data['usmrceno'].sum()),
                    'serious_injuries': int(cluster_data['tezce_zraneno'].sum()),
                    'minor_injuries': int(cluster_data['lehce_zraneno'].sum())
                })

            cluster_profiles.sort(key=lambda x: x['accident_count'], reverse=True)
            results[period] = {
                'profiles': cluster_profiles,
                'n_clusters': len(unique_clusters)
            }

        all_results[eps_km] = results
        print(f"  eps={eps_km}km: {results['Day']['n_clusters']} day, {results['Night']['n_clusters']} night hotspots")

    return all_results


def export_data(df: pd.DataFrame, clustering_results: dict, eps_values: list, output_dir: str):
    """Export accident data and clusters."""

    # Export accidents (Day)
    day_df = df[df['period'] == 'Day']
    day_features = []
    for _, row in day_df.iterrows():
        feature = {
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [row['longitude'], row['latitude']]},
            'properties': {
                'period': 'Day',
                'druh': row['druh'],
                'pricina': row['pricina'],
                'datetime': row['datetime'].isoformat() if pd.notna(row['datetime']) else None,
                'hour': int(row['hour']),
                'usmrceno': int(row['usmrceno']),
                'tezce_zraneno': int(row['tezce_zraneno']),
                'lehce_zraneno': int(row['lehce_zraneno'])
            }
        }
        day_features.append(feature)

    with open(os.path.join(output_dir, 'accidents_day.geojson'), 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection', 'features': day_features}, f)

    # Export accidents (Night)
    night_df = df[df['period'] == 'Night']
    night_features = []
    for _, row in night_df.iterrows():
        feature = {
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [row['longitude'], row['latitude']]},
            'properties': {
                'period': 'Night',
                'druh': row['druh'],
                'pricina': row['pricina'],
                'datetime': row['datetime'].isoformat() if pd.notna(row['datetime']) else None,
                'hour': int(row['hour']),
                'usmrceno': int(row['usmrceno']),
                'tezce_zraneno': int(row['tezce_zraneno']),
                'lehce_zraneno': int(row['lehce_zraneno'])
            }
        }
        night_features.append(feature)

    with open(os.path.join(output_dir, 'accidents_night.geojson'), 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection', 'features': night_features}, f)

    # Export clusters for all eps values
    all_clusters = {}
    for eps_km in eps_values:
        eps_key = str(eps_km)
        all_clusters[eps_key] = {'Day': [], 'Night': []}

        for period in ['Day', 'Night']:
            for profile in clustering_results[eps_km][period]['profiles']:
                all_clusters[eps_key][period].append({
                    'lat': profile['centroid_lat'],
                    'lon': profile['centroid_lon'],
                    'count': profile['accident_count'],
                    'cause': profile['dominant_cause'],
                    'severity': profile['severity_score'],
                    'fatalities': profile['fatalities'],
                    'serious': profile['serious_injuries'],
                    'minor': profile['minor_injuries']
                })

    with open(os.path.join(output_dir, 'clusters.json'), 'w', encoding='utf-8') as f:
        json.dump(all_clusters, f)

    # Export stats
    stats = {
        'total_accidents': len(df),
        'day_accidents': len(day_df),
        'night_accidents': len(night_df),
        'eps_values': eps_values,
        'clusters_by_eps': {
            str(eps): {
                'day': clustering_results[eps]['Day']['n_clusters'],
                'night': clustering_results[eps]['Night']['n_clusters']
            } for eps in eps_values
        }
    }

    with open(os.path.join(output_dir, 'stats.json'), 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2)


def create_html_viewer(output_dir: str, center_lat: float, center_lon: float, eps_values: list):
    """Create HTML viewer with eps distance control."""

    eps_options = ''.join([f'<option value="{eps}">{int(eps*1000)}m</option>' for eps in eps_values])

    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Liberec Accident Analysis</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}

        #map {{ position: absolute; top: 0; left: 0; right: 340px; bottom: 0; }}

        #sidebar {{
            position: absolute; top: 0; right: 0; width: 340px; height: 100%;
            background: #1a1a2e; color: #eee; overflow-y: auto;
            box-shadow: -2px 0 10px rgba(0,0,0,0.3);
        }}

        .header {{
            background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
            padding: 20px; border-bottom: 1px solid #333;
        }}
        .header h1 {{ font-size: 18px; margin-bottom: 5px; }}
        .header p {{ font-size: 12px; color: #888; }}

        .section {{ padding: 15px 20px; border-bottom: 1px solid #333; }}
        .section h2 {{
            font-size: 12px; text-transform: uppercase; letter-spacing: 1px;
            color: #888; margin-bottom: 12px;
        }}

        .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
        .stat-box {{
            background: #16213e; padding: 10px; border-radius: 6px; text-align: center;
        }}
        .stat-box.day {{ border-left: 3px solid #ff8c00; }}
        .stat-box.night {{ border-left: 3px solid #6a5acd; }}
        .stat-value {{ font-size: 20px; font-weight: bold; }}
        .stat-label {{ font-size: 10px; color: #888; margin-top: 2px; }}

        .control-group {{ margin-bottom: 15px; }}
        .control-group label {{ display: block; margin-bottom: 6px; font-size: 12px; color: #ccc; }}
        .control-group select, .control-group input[type="range"] {{
            width: 100%; padding: 8px; border-radius: 4px; border: 1px solid #333;
            background: #16213e; color: #eee; font-size: 14px;
        }}
        .control-group select {{ cursor: pointer; }}
        .control-value {{ text-align: center; margin-top: 5px; color: #ff8c00; font-size: 13px; }}

        .layer-toggle {{
            display: flex; align-items: center; padding: 8px 0; cursor: pointer;
        }}
        .layer-toggle input {{ margin-right: 10px; width: 16px; height: 16px; cursor: pointer; }}
        .layer-toggle label {{ flex: 1; cursor: pointer; font-size: 13px; }}
        .dot {{
            width: 10px; height: 10px; border-radius: 50%;
            display: inline-block; margin-right: 8px;
        }}
        .dot.day {{ background: #ff8c00; }}
        .dot.night {{ background: #6a5acd; }}
        .dot.day-cluster {{ background: #ffa500; border: 2px solid #fff; }}
        .dot.night-cluster {{ background: #483d8b; border: 2px solid #fff; }}

        .cluster-list {{ max-height: 280px; overflow-y: auto; }}
        .cluster-item {{
            background: #16213e; padding: 10px; border-radius: 6px;
            margin-bottom: 6px; cursor: pointer; transition: background 0.2s;
        }}
        .cluster-item:hover {{ background: #1f2b47; }}
        .cluster-item.day {{ border-left: 3px solid #ff8c00; }}
        .cluster-item.night {{ border-left: 3px solid #6a5acd; }}
        .cluster-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }}
        .cluster-count {{ font-size: 16px; font-weight: bold; }}
        .cluster-badge {{
            font-size: 9px; padding: 2px 5px; border-radius: 3px; text-transform: uppercase;
        }}
        .cluster-badge.day {{ background: #ff8c00; color: #000; }}
        .cluster-badge.night {{ background: #6a5acd; color: #fff; }}
        .cluster-cause {{
            font-size: 11px; color: #aaa;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}

        .loading {{
            position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.9); padding: 20px 40px; border-radius: 10px;
            color: #fff; z-index: 9999;
        }}

        @media (max-width: 800px) {{
            #map {{ right: 0; bottom: 45%; }}
            #sidebar {{ top: 55%; width: 100%; height: 45%; }}
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="sidebar">
        <div class="header">
            <h1>Accident Hotspot Analysis</h1>
            <p>Liberec Region - DBSCAN Clustering</p>
        </div>

        <div class="section">
            <h2>Statistics</h2>
            <div class="stats-grid">
                <div class="stat-box day">
                    <div class="stat-value" id="day-accidents">-</div>
                    <div class="stat-label">Day Accidents</div>
                </div>
                <div class="stat-box night">
                    <div class="stat-value" id="night-accidents">-</div>
                    <div class="stat-label">Night Accidents</div>
                </div>
                <div class="stat-box day">
                    <div class="stat-value" id="day-clusters">-</div>
                    <div class="stat-label">Day Hotspots</div>
                </div>
                <div class="stat-box night">
                    <div class="stat-value" id="night-clusters">-</div>
                    <div class="stat-label">Night Hotspots</div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Clustering Settings</h2>
            <div class="control-group">
                <label>Cluster Distance (eps)</label>
                <select id="eps-select">
                    {eps_options}
                </select>
            </div>
            <div class="control-group">
                <label>Minimum Accidents</label>
                <input type="range" id="min-accidents" min="3" max="50" value="5">
                <div class="control-value"><span id="min-value">5</span>+ accidents</div>
            </div>
        </div>

        <div class="section">
            <h2>Layers</h2>
            <div class="layer-toggle">
                <input type="checkbox" id="show-day-accidents" checked>
                <label for="show-day-accidents"><span class="dot day"></span>Day Accidents</label>
            </div>
            <div class="layer-toggle">
                <input type="checkbox" id="show-night-accidents" checked>
                <label for="show-night-accidents"><span class="dot night"></span>Night Accidents</label>
            </div>
            <div class="layer-toggle">
                <input type="checkbox" id="show-day-clusters" checked>
                <label for="show-day-clusters"><span class="dot day-cluster"></span>Day Hotspots</label>
            </div>
            <div class="layer-toggle">
                <input type="checkbox" id="show-night-clusters" checked>
                <label for="show-night-clusters"><span class="dot night-cluster"></span>Night Hotspots</label>
            </div>
        </div>

        <div class="section">
            <h2>Top Hotspots</h2>
            <div class="cluster-list" id="cluster-list"></div>
        </div>
    </div>

    <div class="loading" id="loading">Loading data...</div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const map = L.map('map').setView([{center_lat}, {center_lon}], 10);
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            attribution: '&copy; OSM &copy; CARTO', subdomains: 'abcd', maxZoom: 19
        }}).addTo(map);

        let dayAccidentsLayer = L.layerGroup().addTo(map);
        let nightAccidentsLayer = L.layerGroup().addTo(map);
        let dayClustersLayer = L.layerGroup().addTo(map);
        let nightClustersLayer = L.layerGroup().addTo(map);

        let dayAccidents, nightAccidents, clusters, stats;

        Promise.all([
            fetch('accidents_day.geojson').then(r => r.json()),
            fetch('accidents_night.geojson').then(r => r.json()),
            fetch('clusters.json').then(r => r.json()),
            fetch('stats.json').then(r => r.json())
        ]).then(([day, night, clust, st]) => {{
            dayAccidents = day;
            nightAccidents = night;
            clusters = clust;
            stats = st;

            document.getElementById('day-accidents').textContent = stats.day_accidents.toLocaleString();
            document.getElementById('night-accidents').textContent = stats.night_accidents.toLocaleString();

            // Set default eps to middle value
            const defaultEps = stats.eps_values[Math.floor(stats.eps_values.length / 2)];
            document.getElementById('eps-select').value = defaultEps;

            renderAccidents();
            updateClusters();
            document.getElementById('loading').style.display = 'none';
        }}).catch(err => {{
            document.getElementById('loading').textContent = 'Error: ' + err.message;
        }});

        function renderAccidents() {{
            dayAccidentsLayer.clearLayers();
            nightAccidentsLayer.clearLayers();

            dayAccidents.features.forEach(f => {{
                L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {{
                    radius: 4, color: '#ff8c00', fillColor: '#ff8c00', fillOpacity: 0.6, weight: 1
                }}).bindPopup(`<b>Day Accident</b><br>Type: ${{f.properties.druh || 'N/A'}}<br>Cause: ${{f.properties.pricina || 'N/A'}}`)
                .addTo(dayAccidentsLayer);
            }});

            nightAccidents.features.forEach(f => {{
                L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {{
                    radius: 4, color: '#6a5acd', fillColor: '#6a5acd', fillOpacity: 0.6, weight: 1
                }}).bindPopup(`<b>Night Accident</b><br>Type: ${{f.properties.druh || 'N/A'}}<br>Cause: ${{f.properties.pricina || 'N/A'}}`)
                .addTo(nightAccidentsLayer);
            }});
        }}

        function updateClusters() {{
            const eps = document.getElementById('eps-select').value;
            const minAccidents = parseInt(document.getElementById('min-accidents').value);
            const data = clusters[eps];

            if (!data) return;

            dayClustersLayer.clearLayers();
            nightClustersLayer.clearLayers();

            let dayCount = 0, nightCount = 0;

            // Render day clusters
            data.Day.filter(c => c.count >= minAccidents).forEach(c => {{
                dayCount++;
                const radius = Math.min(8 + Math.sqrt(c.count) * 1.5, 22);
                L.circleMarker([c.lat, c.lon], {{
                    radius, color: '#fff', fillColor: '#ffa500', fillOpacity: 0.9, weight: 2
                }}).bindPopup(`
                    <b>Day Hotspot</b><br>
                    <b>Accidents:</b> ${{c.count}}<br>
                    <b>Cause:</b> ${{c.cause}}<br>
                    <hr style="margin:5px 0">
                    Fatalities: ${{c.fatalities}}<br>
                    Serious: ${{c.serious}}<br>
                    Minor: ${{c.minor}}
                `).addTo(dayClustersLayer);
            }});

            // Render night clusters
            data.Night.filter(c => c.count >= minAccidents).forEach(c => {{
                nightCount++;
                const radius = Math.min(8 + Math.sqrt(c.count) * 1.5, 22);
                L.circleMarker([c.lat, c.lon], {{
                    radius, color: '#fff', fillColor: '#483d8b', fillOpacity: 0.9, weight: 2
                }}).bindPopup(`
                    <b>Night Hotspot</b><br>
                    <b>Accidents:</b> ${{c.count}}<br>
                    <b>Cause:</b> ${{c.cause}}<br>
                    <hr style="margin:5px 0">
                    Fatalities: ${{c.fatalities}}<br>
                    Serious: ${{c.serious}}<br>
                    Minor: ${{c.minor}}
                `).addTo(nightClustersLayer);
            }});

            document.getElementById('day-clusters').textContent = dayCount;
            document.getElementById('night-clusters').textContent = nightCount;

            updateClusterList(data, minAccidents);
        }}

        function updateClusterList(data, minAccidents) {{
            const all = [
                ...data.Day.filter(c => c.count >= minAccidents).map(c => ({{...c, period: 'Day'}})),
                ...data.Night.filter(c => c.count >= minAccidents).map(c => ({{...c, period: 'Night'}}))
            ].sort((a, b) => b.count - a.count).slice(0, 20);

            document.getElementById('cluster-list').innerHTML = all.map(c => `
                <div class="cluster-item ${{c.period.toLowerCase()}}" onclick="map.flyTo([${{c.lat}}, ${{c.lon}}], 15)">
                    <div class="cluster-header">
                        <span class="cluster-count">${{c.count}}</span>
                        <span class="cluster-badge ${{c.period.toLowerCase()}}">${{c.period}}</span>
                    </div>
                    <div class="cluster-cause" title="${{c.cause}}">${{c.cause}}</div>
                </div>
            `).join('');
        }}

        // Event listeners
        document.getElementById('eps-select').addEventListener('change', updateClusters);
        document.getElementById('min-accidents').addEventListener('input', function() {{
            document.getElementById('min-value').textContent = this.value;
            updateClusters();
        }});

        document.getElementById('show-day-accidents').addEventListener('change', function() {{
            this.checked ? map.addLayer(dayAccidentsLayer) : map.removeLayer(dayAccidentsLayer);
        }});
        document.getElementById('show-night-accidents').addEventListener('change', function() {{
            this.checked ? map.addLayer(nightAccidentsLayer) : map.removeLayer(nightAccidentsLayer);
        }});
        document.getElementById('show-day-clusters').addEventListener('change', function() {{
            this.checked ? map.addLayer(dayClustersLayer) : map.removeLayer(dayClustersLayer);
        }});
        document.getElementById('show-night-clusters').addEventListener('change', function() {{
            this.checked ? map.addLayer(nightClustersLayer) : map.removeLayer(nightClustersLayer);
        }});
    </script>
</body>
</html>'''

    with open(os.path.join(output_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html_content)


def main():
    data_path = 'data/nehody_202001-202512.geojson'
    output_dir = 'outputs'

    # Multiple eps values to pre-compute (in km)
    eps_values = [0.1, 0.15, 0.2, 0.3, 0.5]

    os.makedirs(output_dir, exist_ok=True)

    print("Loading data...")
    df = load_geojson(data_path)
    print(f"Loaded {len(df)} accident records")

    print("Preprocessing data...")
    df = preprocess_data(df)
    print(f"Day: {len(df[df['period']=='Day'])}, Night: {len(df[df['period']=='Night'])}")

    print("Clustering at multiple distances...")
    clustering_results = perform_clustering_multi_eps(df, eps_values, min_samples=3)

    print("Exporting data...")
    export_data(df, clustering_results, eps_values, output_dir)

    center_lat = df['latitude'].mean()
    center_lon = df['longitude'].mean()

    print("Creating HTML viewer...")
    create_html_viewer(output_dir, center_lat, center_lon, eps_values)

    print(f"\nDone! Open {output_dir}/index.html via http://localhost:8000")


if __name__ == '__main__':
    main()
