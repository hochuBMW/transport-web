# backend/services.py
from typing import List, Dict, Tuple, Optional
from math import sqrt
from datetime import timedelta
from collections import defaultdict
from utils import haversine_m, parse_time

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
