"""
Tiling and Rendering Engine.

Architecture: Look-Up Table (LUT) Colormapping
----------------------------------------------
To achieve sub-50ms rendering for million-pixel tiles, we avoid conditional logic (if/else)
during the render loop. Instead, we use a pre-computed colormap array (LUT).
1. The colormap is generated once at startup as a (2501, 4) NumPy array.
2. Radar values (mm/h) are scaled and rounded to integers [0...2500].
3. These integers act as direct indices into the LUT: `image = LUT[indices]`.
This is a standard technique in high-performance computer graphics (textures/palettes).

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
    
    Returns:
        np.ndarray: (2501, 4) array mapping values (scaled by 10) to RGBA uint8.
    """
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

def render_tile(data, tile_bounds, product="RQ", flags=None, size=256, interpolation="nearest"):
    """
    Performs inverse projection and colormapping for a single map tile.
    
    Args:
        data: 900x900 radar grid
        tile_bounds: (lon_min, lat_min, lon_max, lat_max)
        product: "RQ" or "RE"
        flags: Optional hail flags for RE
        size: Tile resolution (e.g. 256, 1024)
        interpolation: "nearest" (fast) or "bilinear" (high fidelity, slow on CPU)
    """
    lon_min, lat_min, lon_max, lat_max = tile_bounds
    t_start = time.perf_counter()
    
    # 1. Grid Setup
    px, py = np.meshgrid(np.arange(size), np.arange(size))
    lon = lon_min + (lon_max - lon_min) * px / (size - 1)
    lat = lat_max - (lat_max - lat_min) * py / (size - 1)
    t_grid = time.perf_counter() - t_start

    # 2. Projection
    t_proj_start = time.perf_counter()
    x_rad, y_rad = transformer_wgs84_to_radolan.transform(lon, lat)
    t_proj = time.perf_counter() - t_proj_start

    # 3. Index Calculation (Float coordinates for Bilinear)
    t_idx_start = time.perf_counter()
    x0, y0 = -523462.2, -4658645.0
    fj = (x_rad - x0) / 1000.0 # float col index
    fi = (y_rad - y0) / 1000.0 # float row index
    
    # Create mask for valid pixels (must be inside the 900x900 grid)
    # For bilinear, we need a 1-pixel margin to avoid out-of-bounds
    margin = 1 if interpolation == "bilinear" else 0
    valid_mask = (fi >= 0) & (fi < (900 - margin)) & (fj >= 0) & (fj < (900 - margin))
    t_idx = time.perf_counter() - t_idx_start
    
    # 4. Data Sampling & Colormapping
    t_cmap_start = time.perf_counter()
    image_array = np.zeros((size, size, 4), dtype=np.uint8)

    if interpolation == "bilinear" and product.upper() == "RQ":
        # Vectorated Bilinear Interpolation
        i0 = np.floor(fi[valid_mask]).astype(int)
        i1 = i0 + 1
        j0 = np.floor(fj[valid_mask]).astype(int)
        j1 = j0 + 1
        
        di = fi[valid_mask] - i0
        dj = fj[valid_mask] - j0
        
        # Grab the 4 surrounding pixels
        v00 = data[i0, j0]
        v01 = data[i0, j1]
        v10 = data[i1, j0]
        v11 = data[i1, j1]
        
        # Weighted average
        vals = (v00 * (1 - di) * (1 - dj) +
                v01 * (1 - di) * dj +
                v10 * di * (1 - dj) +
                v11 * di * dj)
    else:
        # Nearest Neighbor (Default)
        vals = data[np.floor(fi[valid_mask]).astype(int), np.floor(fj[valid_mask]).astype(int)]

    # Apply Colormap (or custom RE logic)
    if product.upper() == "RE":
        # RE uses simple categorical colors (no interpolation for flags)
        v_clipped = np.clip(vals, 0.0, 1.0)
        r = (255 * v_clipped).astype(np.uint8)
        g = r
        b = np.full_like(r, 255)
        a = (150 + 50 * v_clipped).astype(np.uint8)
        colors = np.stack([r, g, b, a], axis=-1)
        colors[v_clipped <= 0] = [0, 0, 0, 0]
        if flags is not None:
            # We use nearest neighbor for flags even in bilinear mode
            f_idx_i = np.floor(fi[valid_mask]).astype(int)
            f_idx_j = np.floor(fj[valid_mask]).astype(int)
            f_vals = flags[f_idx_i, f_idx_j]
            hail_mask = (f_vals & 1).astype(bool)
            colors[hail_mask] = [255, 0, 255, 200]
        image_array[valid_mask] = colors
    else:
        # RQ uses LUT
        indices = np.clip(np.round(vals * 10), 0, 2500).astype(int)
        image_array[valid_mask] = RQ_COLORMAP[indices]
    
    t_cmap = time.perf_counter() - t_cmap_start
    
    logger.debug(
        "render_microbench",
        grid=round(t_grid, 4),
        proj=round(t_proj, 4),
        idx=round(t_idx, 4),
        cmap=round(t_cmap, 4),
        interp=interpolation,
        size=size
    )

    return Image.fromarray(image_array, 'RGBA')
