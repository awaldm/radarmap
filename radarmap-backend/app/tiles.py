"""
Tiling and Rendering Engine using look-up table colormapping.

Architecture
----------------------------------------------
To achieve fast rendering, we avoid conditional logic (if/else)
during the render loop. Instead, we use a pre-computed colormap array (LUT).
1. The colormap is generated once at startup as a (2501, 4) NumPy array.
2. Radar values (mm/h) are scaled and rounded to integers [0...2500].
3. These integers act as direct indices into the LUT: `image = LUT[indices]`.

Coordinate System & Precision
-----------------------------
We map the global Web Mercator (EPSG:3857) grid used by map libraries to the 
local RADOLAN Stereographic grid. We use 'Inverse Mapping' (Screen -> Data) 
to ensure every pixel on the user's screen is filled correctly.
"""
from PIL import Image
import numpy as np
import math
import time
from pyproj import Proj, Transformer
from app.logger import get_logger

logger = get_logger()

# Re-usable transformer to avoid overhead
transformer_wgs84_to_radolan = Transformer.from_crs(
    "EPSG:4326", 
    "+proj=stere +lat_0=90 +lat_ts=60 +lon_0=10 +R=6370040 +units=m +no_defs", 
    always_xy=True
)

def num2deg(xtile, ytile, zoom):
    """
    Transform x,y,z to lat/lon as per https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
    """
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return (lat_deg, lon_deg)

def get_tile_bounds(z, x, y):
    """
    Find lat and lon bounds of the supplied points by calling num2deg for two corners.
    """
    lat1, lon1 = num2deg(x, y, z)
    lat2, lon2 = num2deg(x + 1, y + 1, z)
    return (lon1, lat2, lon2, lat1)

def get_rq_colormap():
    """
    Pre-computes a Look-Up Table (LUT) for RQ product (Precipitation Intensity).
    This makes colormap building faster and more straightworward.
    
    Returns:
        np.ndarray: (2501, 4) array mapping values (scaled by 10) to RGBA uint8.
    """
    # Max value is 250 (nodata), scaled by 10 it's 2500. 
    # Array has 2501 slots to accommodate the 0 index.
    cmap = np.zeros((2501, 4), dtype=np.uint8)
    
    thresholds = [0.1, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0]
    colors = [
        (0, 255, 0, 100), (0, 200, 0, 120), (0, 150, 0, 140),
        (255, 255, 0, 160), (255, 204, 0, 180), (255, 102, 0, 200),
        (255, 0, 0, 220), (153, 0, 76, 255)
    ]
    for i in range(1, 2501):
        val = i / 10.0
        if val >= 250: continue
        assigned = False
        for t, c in zip(thresholds, colors):
            if val < t:
                cmap[i] = c
                assigned = True
                break
        if not assigned:
            cmap[i] = colors[-1]
    return cmap

RQ_COLORMAP = get_rq_colormap()

def render_tile(data, tile_bounds, product="RQ", flags=None, size=256):
    """
    Performs inverse projection and colormapping for a single map tile.
    
    Scale Invariance & Boundary Precision:
    - We divide by (size - 1) during interpolation to ensure that pixel 0
      is exactly at the left bound and pixel (size-1) is exactly at the right bound.
    - This prevents 'gaps' or 'slivers' between adjacent map tiles.
    """
    lon_min, lat_min, lon_max, lat_max = tile_bounds
    t_start = time.perf_counter()
    
    # 1. Grid Setup: Create the 'Screen' coordinates
    px, py = np.meshgrid(np.arange(size), np.arange(size))
    
    # Map pixel indices to Lon/Lat (using size-1 for boundary precision)
    lon = lon_min + (lon_max - lon_min) * px / (size - 1)
    lat = lat_max - (lat_max - lat_min) * py / (size - 1)
    t_grid = time.perf_counter() - t_start

    # 2. Projection: Translate Lon/Lat to RADOLAN grid meters
    t_proj_start = time.perf_counter()
    x_rad, y_rad = transformer_wgs84_to_radolan.transform(lon, lat)
    t_proj = time.perf_counter() - t_proj_start

    # 3. Index Calculation: Map meters to array indices [0..899]
    t_idx_start = time.perf_counter()
    x0, y0 = -523462.2, -4658645.0
    j_indices = np.floor((x_rad - x0) / 1000).astype(int)
    i_indices = np.floor((y_rad - y0) / 1000).astype(int)
    valid_mask = (i_indices >= 0) & (i_indices < 900) & (j_indices >= 0) & (j_indices < 900)
    t_idx = time.perf_counter() - t_idx_start
    
    # 4. Colormapping: Apply the Look-Up Table (LUT)
    t_cmap_start = time.perf_counter()
    image_array = np.zeros((size, size, 4), dtype=np.uint8)

    if product.upper() == "RE":
        # RE uses custom logic for Hail flags
        vals = data[i_indices[valid_mask], j_indices[valid_mask]]
        v_clipped = np.clip(vals, 0.0, 1.0)
        r = (255 * v_clipped).astype(np.uint8)
        g = r
        b = np.full_like(r, 255)
        a = (150 + 50 * v_clipped).astype(np.uint8)
        colors = np.stack([r, g, b, a], axis=-1)
        if flags is not None:
            f_vals = flags[i_indices[valid_mask], j_indices[valid_mask]]
            hail_mask = (f_vals & 1).astype(bool)
            colors[hail_mask] = [255, 0, 255, 200]
        image_array[valid_mask] = colors
    else:
        # RQ uses the high-performance LUT
        vals = data[i_indices[valid_mask], j_indices[valid_mask]]
        indices = np.clip(np.round(vals * 10), 0, 2500).astype(int)
        image_array[valid_mask] = RQ_COLORMAP[indices]
    
    t_cmap = time.perf_counter() - t_cmap_start
    
    logger.debug(
        "render_microbench",
        grid=round(t_grid, 4),
        proj=round(t_proj, 4),
        idx=round(t_idx, 4),
        cmap=round(t_cmap, 4),
        size=size
    )

    return Image.fromarray(image_array, 'RGBA')
