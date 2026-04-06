# backend/main.py
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import timedelta
from typing import Any, Dict, List
import uvicorn
import logging
from shapely.geometry import MultiPoint, mapping

from models import AnalyzeRequest
from utils import parse_time, point_in_analysis_geometry
from services import (
    calculate_statistics,
    region_growing_clusters,
    aggregate_plot_data,
    snap_features_by_engine,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Transport Analysis API",
    description="API для анализа транспортных данных и выявления зон заторов",
    version="2.1.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "name": "Transport Analysis API",
        "version": "2.1.0",
        "status": "online"
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        gj = req.geojson
        features = gj.get("features", [])
        
        if not features:
            raise HTTPException(status_code=400, detail="No features found in GeoJSON")
        
        start_dt = parse_time(req.start) if req.start else None
        end_dt = parse_time(req.end) if req.end else None
        
        if start_dt and end_dt and start_dt > end_dt:
            raise HTTPException(status_code=400, detail="Start time must be before end time")

        fmt_errors = 0
        filtered_points = []
        speeds = []
        dropped = 0
        slow_candidates = []
        slow_indices = []

        # Process features
        for feat in features:
            geom = feat.get("geometry")
            props = feat.get("properties", {})
            
            if not geom or geom.get("type") != "Point":
                continue
            
            coords = geom.get("coordinates")
            if not coords or len(coords) < 2:
                continue
            
            try:
                lon, lat = float(coords[0]), float(coords[1])
            except (TypeError, ValueError):
                continue

            if req.analysis_geometry and not point_in_analysis_geometry(lon, lat, req.analysis_geometry):
                continue

            # Parse time and apply +8 hours offset
            dt = parse_time(str(props.get("time")))
            if dt is None:
                fmt_errors += 1
                continue
            
            # Apply time offset (+8 hours)
            dt = dt + timedelta(hours=8)
            
            # Apply filters
            if (start_dt and dt < start_dt) or (end_dt and dt > end_dt):
                continue
            
            # Apply route filter
            if req.routes and str(props.get("route_num")) not in req.routes:
                continue

            try:
                speed = float(props.get("speed", 0))
                if speed < 0: speed = 0
            except:
                continue

            if (not req.include_zero) and speed <= 1.0:
                dropped += 1
                continue

            # Accept point
            idx = len(filtered_points)
            filtered_points.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {**props, "speed": speed, "time": dt.isoformat()}
            })
            speeds.append(speed)

            if speed <= req.speed_thresh:
                slow_candidates.append([lon, lat])
                slow_indices.append(idx)

        if req.map_matching and filtered_points:
            filtered_points = snap_features_by_engine(
                filtered_points,
                engine=req.snap_engine,
                roads_path=req.roads_geojson_path,
                tolerance_m=req.snap_tolerance_m,
            )
            # Rebuild slow candidates with potentially new coordinates
            slow_candidates = []
            for i in slow_indices:
                feat = filtered_points[i]
                coords = feat.get("geometry", {}).get("coordinates")
                if coords:
                    slow_candidates.append(coords)

        # Calculate Congestion Index (1-10)
        # Assuming 40 km/h is free flow speed.
        avg_speed = sum(speeds) / len(speeds) if speeds else 0
        congestion_index = 1
        if avg_speed > 0:
            congestion_index = min(10, max(1, round(11 - (avg_speed / 40) * 10)))
        elif speeds:
            congestion_index = 10 # 0 avg speed means max congestion

        result = {
            "avg_speed": avg_speed if speeds else None,
            "congestion_index": congestion_index,
            "dropped": dropped,
            "count": len(filtered_points),
            "filtered_geojson": {"type": "FeatureCollection", "features": filtered_points},
            "congestion_zones": [],
            "plot": {"times": [], "speeds": []},
            "statistics": calculate_statistics(speeds) if speeds else {},
            "warnings": [],
        }

        if fmt_errors:
            result["warnings"].append(f"Could not parse {fmt_errors} time values")

        if req.map_matching and req.snap_engine == "qgis":
            rpath = (req.roads_geojson_path or os.environ.get("ROADS_GEOJSON_PATH") or "").strip()
            rpath = os.path.expanduser(rpath)
            if not rpath or not os.path.isfile(rpath):
                result["warnings"].append(
                    "Привязка к графу: не задан или не найден файл дорог (roads_geojson_path или ROADS_GEOJSON_PATH)."
                )
        
        if not filtered_points:
            result["warnings"].append("No points matching criteria")
            return result

        # Plot data
        raw_times = [f["properties"]["time"] for f in filtered_points]
        agg_times, agg_speeds = aggregate_plot_data(raw_times, speeds, interval_minutes=15)
        result["plot"] = {
            "times": agg_times, 
            "speeds": agg_speeds,
            "raw_times": raw_times,
            "raw_speeds": speeds
        }

        # Clustering
        if slow_candidates:
            clusters = region_growing_clusters(slow_candidates, req.eps_m, req.min_pts)
            for cluster_idx, cluster in enumerate(clusters if req.return_all_clusters else clusters[:1]):
                cluster_coords = [slow_candidates[i] for i in cluster]
                mp = MultiPoint(cluster_coords)
                if not mp.is_empty:
                    hull = mp.convex_hull
                    hull_gj = mapping(hull)
                    hull_gj["properties"] = {
                        "cluster_size": len(cluster),
                        "cluster_index": cluster_idx,
                        "avg_speed": sum(speeds[slow_indices[i]] for i in cluster) / len(cluster)
                    }
                    result["congestion_zones"].append(hull_gj)
            
            if result["congestion_zones"]:
                result["congestion"] = result["congestion_zones"][0]

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in analyze: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
