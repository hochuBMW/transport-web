# backend/services.py
from typing import List, Dict, Tuple, Optional, Any
from math import sqrt
from datetime import datetime, timedelta
from collections import defaultdict
import logging
import os
import requests
from utils import haversine_m, parse_time

logger = logging.getLogger(__name__)

OSRM_MATCH_URL = "http://router.project-osrm.org/match/v1/driving/{coords}"

def snap_features(features: List[Dict[str, Any]], max_chunk_size=90) -> List[Dict[str, Any]]:
    """Snaps a list of features to the road network using OSRM Match API"""
    if not features:
        return features

    vehicles = defaultdict(list)
    for i, feat in enumerate(features):
        props = feat.get("properties", {})
        veh_id = props.get("gos_num") or props.get("plate") or props.get("bnum") or "unknown"
        vehicles[veh_id].append((i, feat))

    snapped_features = features.copy()
    
    for veh_id, v_list in vehicles.items():
        v_list.sort(key=lambda x: parse_time(x[1]["properties"].get("time", "")) or datetime.min)
        
        for i in range(0, len(v_list), max_chunk_size):
            chunk = v_list[i:i + max_chunk_size]
            if len(chunk) < 2:
                continue
                
            coords_str = ";".join([f"{f[1]['geometry']['coordinates'][0]},{f[1]['geometry']['coordinates'][1]}" for f in chunk])
            
            radiuses = ";".join(["50" for _ in chunk])
            
            url = f"{OSRM_MATCH_URL.format(coords=coords_str)}?overview=false&radiuses={radiuses}&gaps=ignore"
            
            try:
                response = requests.get(
                    url, 
                    headers={"User-Agent": "TransportWebMapMatcher/1.0 (Student Diplome)"},
                    timeout=5
                )
                if response.status_code == 429:
                    print("Внимание: достигнут лимит OSRM (Too Many Requests). Прекращаем привязку оставшихся точек.")
                    return snapped_features
                    
                if response.status_code == 200:
                    res_json = response.json()
                    if res_json.get("code") == "Ok":
                        tracepoints = res_json.get("tracepoints", [])
                        for idx, trace in enumerate(tracepoints):
                            orig_index = chunk[idx][0]
                            if trace is not None and "location" in trace:
                                new_coords = trace["location"]
                                snapped_features[orig_index]["geometry"]["coordinates"] = new_coords
                                snapped_features[orig_index]["properties"]["snapped"] = True
            except Exception as e:
                pass # Ignore matching errors and keep original coords

    return snapped_features


def snap_features_by_engine(
    features: List[Dict[str, Any]],
    engine: str,
    roads_path: Optional[str] = None,
    tolerance_m: float = 50.0,
) -> List[Dict[str, Any]]:
    """
    engine: "osrm" — публичный OSRM Match; "qgis" — PyQGIS snap to layer (нужен QGIS Python).
    """
    if not features:
        return features
    eng = (engine or "osrm").strip().lower()
    if eng == "qgis":
        path = (roads_path or os.environ.get("ROADS_GEOJSON_PATH") or "").strip()
        if not path:
            logger.warning("snap_engine=qgis: задайте roads_geojson_path в запросе или ROADS_GEOJSON_PATH в .env")
            return features
        # Граф дорог: Shapely + STRtree (обычный Python). PyQGIS — только если USE_QGIS_SNAP=1
        if os.environ.get("USE_QGIS_SNAP", "").lower() in ("1", "true", "yes"):
            try:
                from qgis_snap_service import snap_features_pyqgis, qgis_available

                if qgis_available():
                    return snap_features_pyqgis(features, path, tolerance_m=tolerance_m)
            except Exception as e:
                logger.warning("QGIS snap отключён, используем граф (Shapely): %s", e)
        from road_graph_snap import snap_features_to_roads_geojson

        return snap_features_to_roads_geojson(features, path, tolerance_m=tolerance_m)
    return snap_features(features)


def calculate_statistics(speeds: List[float]) -> Dict[str, float]:
    """Calculate comprehensive speed statistics."""
    if not speeds:
        return {}
    
    sorted_speeds = sorted(speeds)
    n = len(sorted_speeds)
    mean_val = sum(speeds) / n
    
    return {
        "min": min(speeds),
        "max": max(speeds),
        "mean": mean_val,
        "median": sorted_speeds[n // 2] if n % 2 == 1 else (sorted_speeds[n // 2 - 1] + sorted_speeds[n // 2]) / 2,
        "std": sqrt(sum((x - mean_val) ** 2 for x in speeds) / n) if n > 1 else 0,
        "q25": sorted_speeds[n // 4] if n >= 4 else sorted_speeds[0],
        "q75": sorted_speeds[3 * n // 4] if n >= 4 else sorted_speeds[-1],
    }

def region_growing_clusters(
    points: List[List[float]], 
    eps_m: float, 
    min_pts: int
) -> List[List[int]]:
    """Optimized region-growing clustering algorithm."""
    n = len(points)
    if n == 0:
        return []
    
    if n < 100:
        return _simple_clustering(points, eps_m, min_pts)
    
    return _spatial_grid_clustering(points, eps_m, min_pts)

def _simple_clustering(points, eps_m, min_pts):
    n = len(points)
    visited = [False] * n
    clusters = []

    for i in range(n):
        if visited[i]: continue
        
        stack = [i]
        cluster = []
        while stack:
            cur = stack.pop()
            if visited[cur]: continue
            
            visited[cur] = True
            cluster.append(cur)
            lon1, lat1 = points[cur]
            
            for j in range(n):
                if visited[j]: continue
                lon2, lat2 = points[j]
                if haversine_m(lon1, lat1, lon2, lat2) <= eps_m:
                    stack.append(j)
        
        if len(cluster) >= min_pts:
            clusters.append(cluster)
    
    clusters.sort(key=len, reverse=True)
    return clusters

def _spatial_grid_clustering(points, eps_m, min_pts):
    n = len(points)
    cell_size = max(eps_m / 111000 * 2, 0.001)
    grid = defaultdict(list)
    
    for i, (lon, lat) in enumerate(points):
        grid[(int(lon / cell_size), int(lat / cell_size))].append(i)
    
    visited = [False] * n
    clusters = []
    
    for i in range(n):
        if visited[i]: continue
        
        stack = [i]
        cluster = []
        while stack:
            cur = stack.pop()
            if visited[cur]: continue
            
            visited[cur] = True
            cluster.append(cur)
            lon1, lat1 = points[cur]
            cx, cy = int(lon1 / cell_size), int(lat1 / cell_size)
            
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    for j in grid.get((cx + dx, cy + dy), []):
                        if not visited[j]:
                            lon2, lat2 = points[j]
                            if haversine_m(lon1, lat1, lon2, lat2) <= eps_m:
                                stack.append(j)
        
        if len(cluster) >= min_pts:
            clusters.append(cluster)
    
    clusters.sort(key=len, reverse=True)
    return clusters

def aggregate_plot_data(
    times: List[str],
    speeds: List[float],
    interval_minutes: int = 15
) -> Tuple[List[str], List[float]]:
    """Aggregate plot data into time intervals."""
    if not times or not speeds or len(times) != len(speeds):
        return times, speeds
    
    parsed_data = []
    for i, t in enumerate(times):
        dt = parse_time(t) if isinstance(t, str) else t
        if dt: parsed_data.append((dt, speeds[i]))
    
    if not parsed_data: return times, speeds
    
    min_time = min(d[0] for d in parsed_data)
    interval_delta = timedelta(minutes=interval_minutes).total_seconds()
    buckets = defaultdict(list)
    
    for dt, speed in parsed_data:
        bucket_idx = int((dt - min_time).total_seconds() / interval_delta)
        buckets[bucket_idx].append(speed)
    
    agg_times, agg_speeds = [], []
    for b_idx in sorted(buckets.keys()):
        interval_start = min_time + timedelta(seconds=b_idx * interval_delta)
        agg_times.append(interval_start.isoformat())
        agg_speeds.append(sum(buckets[b_idx]) / len(buckets[b_idx]))
    
    return agg_times, agg_speeds
