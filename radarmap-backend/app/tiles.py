"""
Geospatial Utilities & Shared Constants.

This module serves as the 'Single Source of Truth' for geospatial math and radar
visualization constants used across different rendering paths (CPU, CUDA, etc.).

To ensure that our symmetric rendering providers (see `app/renderers/`) produce
identical visual results, they must share the same projection parameters and
colormapping logic defined here.

Contents:
---------
1. Coordinate Transforms:
   - `transformer_wgs84_to_radolan`: A pre-configured PyProj Transformer that
     maps GPS coordinates (WGS84) to the German Radar Grid (Stereographic).
   - `num2deg` / `get_tile_bounds`: Standard Slippy Map math to convert XYZ
     tile indices into Lat/Lon bounding boxes.

2. Visualization:
   - `get_rq_colormap`: Generates a high-performance Look-Up Table (LUT). This
     LUT allows renderers to map precipitation values to RGBA colors in O(1) time
     without conditional branching.

"""

import math

import numpy as np
from pyproj import Transformer

from app.logger import get_logger

logger = get_logger()

# Shared Coordinate Transformer
# Source: EPSG:4326 (WGS84)
# Target: DWD RADOLAN Standard (Polar Stereographic)
transformer_wgs84_to_radolan = Transformer.from_crs(
    "EPSG:4326",
    "+proj=stere +lat_0=90 +lat_ts=60 +lon_0=10 +R=6370040 +units=m +no_defs",
    always_xy=True,
)


def num2deg(xtile, ytile, zoom):
    """
    Translates Slippy Map (X, Y, Z) indices to Latitude/Longitude.
    Reference: https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
    """
    n = 2.0**zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return (lat_deg, lon_deg)


def get_tile_bounds(z, x, y):
    """
    Calculates the Lat/Lon bounding box for a standard 256x256 map tile.
    """
    lat1, lon1 = num2deg(x, y, z)
    lat2, lon2 = num2deg(x + 1, y + 1, z)
    return (lon1, lat2, lon2, lat1)


def get_rq_colormap():
    """
    Pre-computes a Look-Up Table (LUT) for radar intensity mapping.
    Maps values [0.0 - 250.0] mm/h to (R, G, B, A) bytes.
    """
    cmap = np.zeros((2501, 4), dtype=np.uint8)
    thresholds = [0.1, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0]
    colors = [
        (0, 255, 0, 100),
        (0, 200, 0, 120),
        (0, 150, 0, 140),
        (255, 255, 0, 160),
        (255, 204, 0, 180),
        (255, 102, 0, 200),
        (255, 0, 0, 220),
        (153, 0, 76, 255),
    ]
    for i in range(1, 2501):
        val = i / 10.0
        if val >= 250:
            continue
        assigned = False
        for t, c in zip(thresholds, colors, strict=False):
            if val < t:
                cmap[i] = c
                assigned = True
                break
        if not assigned:
            cmap[i] = colors[-1]
    return cmap


# Global reference used by both CPU and GPU providers
RQ_COLORMAP = get_rq_colormap()
