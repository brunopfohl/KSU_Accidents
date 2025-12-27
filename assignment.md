# Project Specification: Spatio-Temporal Accident Analysis (Liberec)

## 1. Objective

Create a Python data analysis pipeline to analyze traffic accident clusters in Liberec. The goal is to perform **Spatio-Temporal Clustering** to distinguish between "Daytime" and "Nighttime" accident hotspots and visualize them on an interactive map.

## 2. Project Structure

The project is organized as follows:

```text
project_root/
│
├── data/
│   └── nehody_202502-202512.geojson  # Source data
│
├── outputs/
│   └── accident_map_day_night.html   # Final interactive map
│
└── main.py                           # The script to be generated

```

## 3. Data Description

The input file is a GeoJSON containing point features.
**Key attributes in `properties`:**

* `datum`: ISO 8601 timestamp (e.g., `2025-02-25T22:00:00+01:00`).
* `druh`: Type of accident (string).
* `pricina`: Cause of accident (string).
* `usmrceno`, `tezce_zraneno`, `lehce_zraneno`: Integers indicating severity.
* `hmotna_skoda`: String (e.g., "35 000 Kč").

## 4. Implementation Steps

### Step 1: Data Loading & Preprocessing

* Load the GeoJSON file from `data/nehody_202502-202512.geojson`.
* Convert it into a Pandas DataFrame.
* **Time Extraction:** Parse the `datum` column to extract the **Hour** (0-23).
* **Day/Night Segmentation:** Create a new column `period`:
* **Day:** 06:00 to 18:59
* **Night:** 19:00 to 05:59



### Step 2: Unsupervised Learning (K-Means Clustering)

Perform clustering **separately** for the "Day" dataset and the "Night" dataset.

* **Algorithm:** K-Means (from `sklearn`).
* **Features:** Latitude and Longitude.
* **Number of Clusters (k):** Set  for both Day and Night (to find top 10 hotspots for each period).
* **Centroid Profiling:** For each cluster found, determine the **Dominant Accident Cause** (the most frequent value in `pricina` column within that cluster).

### Step 3: Visualization (Folium Map)

Generate an interactive map (`outputs/accident_map_day_night.html`) centered on Liberec.

**Requirements for the map:**

1. **Base Map:** Use 'CartoDB positron' or 'OpenStreetMap'.
2. **Layer Control:** Implement toggleable layers:
* Layer 1: "Daytime Accidents"
* Layer 2: "Nighttime Accidents"
* Layer 3: "Day Clusters (Centroids)"
* Layer 4: "Night Clusters (Centroids)"


3. **Color Coding:**
* **Daytime:** Use **Orange/Amber** colors (representing Sun/Traffic).
* **Nighttime:** Use **Dark Blue/Purple** colors (representing Night).


4. **Markers:**
* Plot individual accidents as small circle markers.
* Plot **Cluster Centroids** as larger icons (e.g., Info sign).


5. **Popups:**
* When clicking a Cluster Centroid, show a popup with:
* "Cluster Type: Day" or "Night"
* "Dominant Cause: [Most frequent cause]"
* "Total Accidents: [Count]"





## 5. Technical Stack

* Python 3.x
* Pandas, GeoPandas (optional, regular json lib is fine too)
* Scikit-learn (KMeans)
* Folium

## 6. Output

Provide the full Python code in `main.py` that runs without errors, creates the `outputs` directory if it doesn't exist, and generates the map.