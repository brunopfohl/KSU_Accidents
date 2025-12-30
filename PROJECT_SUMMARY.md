# KSU_Accidents - Complete Project Summary

## Repository Information
- **GitHub**: https://github.com/brunopfohl/KSU_Accidents
- **Branch**: master
- **Purpose**: Traffic accident hotspot analysis for Liberec region (academic project)
- **Language**: Python + JavaScript (frontend)

---

## Directory Structure

```
KSU_Accidents/
├── data/
│   └── nehody_202001-202512.geojson    # Source data: 28,013 traffic accidents
├── outputs/
│   ├── index.html                       # Interactive web UI (Leaflet map)
│   ├── clusters.geojson                 # Legacy DBSCAN output
│   ├── clusters.json                    # Legacy cluster data
│   ├── accidents_day.geojson            # Legacy day accidents
│   ├── accidents_night.geojson          # Legacy night accidents
│   └── stats.json                       # Legacy statistics
├── server.py                            # Flask backend (main application)
├── main.py                              # Legacy script (original K-Means implementation)
├── assignment.md                        # Original assignment specification
├── PROJECT_SUMMARY.md                   # This file
└── .gitignore
```

---

## Data Description

### Source: `data/nehody_202001-202512.geojson`
- **Format**: GeoJSON with Point features
- **Records**: 28,013 traffic accidents
- **Time Range**: January 2020 - December 2025
- **Region**: Liberec, Czech Republic

### Key Attributes
| Attribute | Type | Description |
|-----------|------|-------------|
| `datum` | ISO 8601 | Timestamp (e.g., `2025-02-25T22:00:00+01:00`) |
| `druh` | string | Accident type |
| `pricina` | string | Cause of accident |
| `usmrceno` | int | Fatalities |
| `tezce_zraneno` | int | Serious injuries |
| `lehce_zraneno` | int | Minor injuries |
| `hmotna_skoda` | string | Property damage (e.g., "35 000 Kč") |
| `coordinates` | [lon, lat] | Geographic location |

### Derived Fields (computed in server.py)
| Field | Formula | Description |
|-------|---------|-------------|
| `period` | hour 6-18 = "Day", else "Night" | Time period |
| `severity_score` | fatalities×100 + serious×10 + minor×1 | Weighted severity |

### Data Split
- **Day accidents**: 17,334 (06:00-18:59)
- **Night accidents**: 10,679 (19:00-05:59)
- **Expected night ratio**: ~38%

---

## Architecture

### Backend: `server.py` (Flask)

```
Flask App (port 5000)
├── /                          → Serves index.html
├── /api/stats                 → Basic statistics, accident types
├── /api/accidents             → Filtered accident points (GeoJSON)
├── /api/cluster               → DBSCAN clustering
└── /api/hotspots              → Getis-Ord Gi* analysis
```

### Frontend: `outputs/index.html`
- **Map**: Leaflet.js with CartoDB tiles
- **UI**: Sidebar with controls, statistics, results list
- **Layers**: Day/Night accidents, Day/Night hotspots, Anomalies

---

## Analysis Methods

### 1. DBSCAN Clustering (Exploratory)
- **Library**: scikit-learn
- **Parameters**:
  - `eps`: Cluster distance in km (0.05-2.0, default 0.2)
  - `min_samples`: Minimum points per cluster (2-10000, default 3)
- **Use Case**: Quick visual exploration of accident density

### 2. Getis-Ord Gi* (Statistical Hotspots) ⭐ PRIMARY METHOD
- **Library**: PySAL (esda, libpysal)
- **Method**: Local Getis-Ord Gi* statistic with analytical p-values
- **Parameters**:
  - `cell_size`: Grid cell size in meters (100-1000, default 300)
  - `metric`: What to analyze (`count`, `severity_score`, `hmotna_skoda`)
  - `k`: KNN neighbors for spatial weights (hardcoded k=5)
  - `alpha`: Significance level (hardcoded 0.05)

#### How Getis-Ord Works:
1. Create grid covering study area
2. Aggregate accidents to grid cells
3. Compute KNN spatial weights
4. Calculate Gi* z-scores (analytical, permutations=0)
5. Mark cells with p < 0.05 as significant hotspots
6. Positive z-score = hotspot (high values clustered)

#### Metric-Specific Behavior:
- **count**: Includes all cells with accidents
- **severity_score**: Only includes cells with injuries (severity > 0)
- **hmotna_skoda**: Only includes cells with damage > 0

### 3. Day/Night Anomaly Detection ⭐ GETIS-ORD ON RATIO
- **Method**: Getis-Ord Gi* applied to night_ratio per cell
- **Formula**: `night_ratio = night_count / (day_count + night_count)`
- **Interpretation**:
  - High z-score (positive) = **Night anomaly cluster** (more night accidents than expected)
  - Low z-score (negative) = **Day anomaly cluster** (fewer night accidents than expected)
- **Minimum**: 5 accidents per cell to be analyzed

#### Previous Method (Replaced):
Originally used binomial test per cell - this was statistically valid but:
- Ignored spatial autocorrelation
- Had multiple testing problem
- Found isolated cells, not coherent clusters

The Getis-Ord approach is academically superior because it finds **spatial clusters** of anomalous day/night patterns.

---

## API Reference

### GET /api/stats
Returns basic statistics and accident types.
```json
{
  "total": 28013,
  "day": 17334,
  "night": 10679,
  "center_lat": 50.xxx,
  "center_lon": 15.xxx,
  "types": [{"name": "...", "count": ...}]
}
```

### GET /api/accidents
Query params: `severity`, `min_damage`, `types` (pipe-separated)
```json
{
  "day": {"type": "FeatureCollection", "features": [...]},
  "night": {"type": "FeatureCollection", "features": [...]},
  "day_count": 17334,
  "night_count": 10679
}
```

### GET /api/cluster (DBSCAN)
Query params: `eps`, `min_samples`, `severity`, `min_damage`, `types`
```json
{
  "eps": 0.2,
  "min_samples": 3,
  "day": [{cluster_object}],
  "night": [{cluster_object}],
  "day_count": 42,
  "night_count": 35
}
```

### GET /api/hotspots (Getis-Ord Gi*)
Query params: `cell_size`, `metric`, `severity`, `min_damage`, `types`
```json
{
  "cell_size": 300,
  "metric": "count",
  "day_hotspots": [{
    "lat": 50.xxx,
    "lon": 15.xxx,
    "count": 45,
    "metric_value": 45,
    "z_score": 3.21,
    "p_value": 0.0013,
    "fatalities": 0,
    "serious": 2,
    "minor": 5,
    "damage": 450000,
    "severity_score": 25,
    "cause": "nedodržení bezpečné vzdálenosti"
  }],
  "night_hotspots": [...],
  "anomalies": [{
    "lat": 50.xxx,
    "lon": 15.xxx,
    "day_count": 12,
    "night_count": 28,
    "total": 40,
    "observed_night_ratio": 0.70,
    "expected_night_ratio": 0.38,
    "z_score": 2.85,
    "p_value": 0.0044,
    "type": "night_anomaly"
  }],
  "total_anomalies": 135,
  "night_anomalies": 77,
  "day_anomalies": 58
}
```

---

## Performance Optimizations

### Problem: Initial Getis-Ord took ~30 seconds

### Solutions Applied:

1. **Analytical p-values** (permutations=0)
   - Before: permutations=999 (slow Monte Carlo simulation)
   - After: analytical formula (Getis & Ord 1992) - academically standard

2. **Vectorized grid creation**
   - Before: Python loop creating Shapely boxes → 1.85s
   - After: NumPy meshgrid + point geometries → 0.03s

3. **Mathematical cell assignment**
   - Before: `gpd.sjoin()` spatial join → 8.44s
   - After: Direct calculation `cell_id = row * cols + col` → 0.90s

4. **Grid caching**
   - Grids are cached by cell_size

### Final Performance:
- ~3 seconds for full Getis-Ord analysis (was ~12+ seconds)

---

## Key Technical Decisions

### 1. Why Getis-Ord over DBSCAN?
| Aspect | DBSCAN | Getis-Ord Gi* |
|--------|--------|---------------|
| Statistical significance | No | Yes (p-values) |
| Academic rigor | Low | High (standard method) |
| Cluster boundaries | Arbitrary | Grid-based, reproducible |
| Sensitivity analysis | Hard | Easy (change cell size) |

### 2. Why analytical p-values?
- Original Getis & Ord (1992) paper used analytical
- Permutation tests came later for robustness
- With large n (thousands of cells), analytical is valid and fast
- Academically defensible

### 3. Why metric-based filtering?
- When analyzing `severity_score`, only include cells with injuries
- Otherwise Gi* finds "clusters" where severity=0 > 0 (meaningless)
- Same for `hmotna_skoda` (damage)

### 4. Why Getis-Ord for anomalies?
- Binomial test per cell: statistically valid but no spatial structure
- Getis-Ord on ratio: finds **spatial clusters** of temporal anomalies
- More robust to noise, academically standard approach

---

## Filters Available

### Accident Filters (applied before analysis)
- **Severity**: All, With Injury, Serious+, Fatal Only
- **Min Damage**: Minimum property damage per accident
- **Types**: Multi-select accident types (pipe-separated in URL)

### Display Filters (DBSCAN only)
- **Min Display**: Minimum accidents per hotspot to show
- **Min Damage**: Minimum total damage per hotspot

---

## UI Features

### Mode Toggle
- DBSCAN: Quick exploratory clustering
- Getis-Ord Gi*: Statistical hotspot analysis

### Layers (toggleable)
- Day Accidents (orange dots)
- Night Accidents (purple dots)
- Day Hotspots (orange circles with white border)
- Night Hotspots (purple circles with white border)
- Day/Night Anomalies (green circles) - Getis-Ord mode only

### Statistics Panel
- Day/Night accident counts
- Day/Night hotspot counts
- Anomaly counts (Getis-Ord mode)

### Results List
- Top hotspots sorted by z-score (count) or metric_value (severity/damage)
- Anomalies sorted by absolute z-score
- Click to fly to location

---

## Dependencies

```
flask
flask-cors
pandas
numpy
scikit-learn
geopandas
shapely
libpysal
esda
scipy
```

---

## Running the Application

```bash
cd KSU_Accidents
python server.py
# Server runs at http://localhost:5000
```

---

## Academic Context

This is a university project (KSU = likely a course code) focused on:
- Spatio-temporal clustering of traffic accidents
- Distinguishing day vs night patterns
- Statistical hotspot detection
- Interactive visualization

The implementation evolved from simple K-Means (assignment requirement) through DBSCAN to proper Getis-Ord Gi* statistical analysis, which is the academically standard method for hotspot detection in spatial epidemiology and crime analysis.

---

## Conversation History Summary

### Major Milestones:

1. **Initial Implementation**: K-Means clustering per assignment spec
2. **Switch to DBSCAN**: More flexible density-based clustering
3. **Flask Backend**: Real-time parameter adjustment
4. **Bug Fixes**:
   - Type filter comma delimiter (types contain commas) → switched to pipe `|`
   - Empty type selection behavior
5. **Getis-Ord Implementation**: Added statistical rigor
6. **Performance Optimization**: 30s → 3s through vectorization and analytical p-values
7. **Metric Selection**: Added "Analyze by" dropdown (count, severity, damage)
8. **Metric-based Filtering**: Only analyze cells where metric > 0
9. **Anomaly Detection Upgrade**: Binomial test → Getis-Ord on night ratio

### Key User Insights:
- "We want something academically valid, not pseudo-shit"
- "Higher severity score = worse" clarification
- "Why do I see severity=0 hotspots?" → led to metric-based filtering
- "Is the anomaly detection cluster analysis?" → led to Getis-Ord on ratio

---

## Current State (as of last session)

- Server running with all features implemented
- Getis-Ord Gi* for hotspot detection ✅
- Getis-Ord on night ratio for anomaly detection ✅
- Three metrics: count, severity_score, hmotna_skoda ✅
- Performance optimized (~3s) ✅
- All uncommitted changes in server.py and outputs/index.html

---

## Future Improvements (Discussed but not implemented)

1. **K parameter exposure**: Allow users to adjust KNN neighbors (currently k=5)
2. **Significance tiers visualization**: Show p<0.01, p<0.05, p<0.10 with different colors
3. **KDE layer**: Kernel Density Estimation for smooth visualization
4. **SaTScan integration**: Space-time scan statistics for formal cluster detection
5. **Multiple testing correction**: FDR/Bonferroni for anomaly detection
