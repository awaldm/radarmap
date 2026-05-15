from PIL import Image
import numpy as np
import math
from pyproj import Proj, Transformer

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
    Creates a colormap for RQ product (Precipitation Intensity).
    Returns an array of shape (2501, 4) mapping values (scaled by 10) to RGBA.
    """
    cmap = np.zeros((2501, 4), dtype=np.uint8)
    thresholds = [0.1, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0]
    colors = [
        (0, 255, 0, 100),   # < 0.1
        (0, 200, 0, 120),   # 0.1 - 1.0
        (0, 150, 0, 140),   # 1.0 - 2.5
        (255, 255, 0, 160), # 2.5 - 5.0
        (255, 204, 0, 180), # 5.0 - 10.0
        (255, 102, 0, 200), # 10.0 - 25.0
        (255, 0, 0, 220),   # 25.0 - 50.0
        (153, 0, 76, 255)   # > 50.0
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
    Performs inverse projection to map a {size}x{size} Web Mercator tile to the 900x900 RADOLAN grid.
    """
    lon_min, lat_min, lon_max, lat_max = tile_bounds
    
    # Create a grid of pixel coordinates in the tile.
    px, py = np.meshgrid(np.arange(size), np.arange(size))
    
    # Map pixel coordinates to lon/lat
    lon = lon_min + (lon_max - lon_min) * px / (size - 1)
    lat = lat_max - (lat_max - lat_min) * py / (size - 1)

    # Transform lon/lat to RADOLAN projection coordinates
    x_rad, y_rad = transformer_wgs84_to_radolan.transform(lon, lat)

    # RADOLAN grid parameters (magic numbers)
    x0, y0 = -523462.2, -4658645.0
    
    # Map RADOLAN coordinates to grid indices
    j_indices = np.floor((x_rad - x0) / 1000).astype(int)
    i_indices = np.floor((y_rad - y0) / 1000).astype(int)

    # Valid indices mask (900x900 national grid)
    valid_mask = (i_indices >= 0) & (i_indices < 900) & (j_indices >= 0) & (j_indices < 900)
    
    # Initialize empty RGBA image array
    image_array = np.zeros((size, size, 4), dtype=np.uint8)

    if product.upper() == "RE":
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
        vals = data[i_indices[valid_mask], j_indices[valid_mask]]
        indices = np.clip(np.round(vals * 10), 0, 2500).astype(int)
        image_array[valid_mask] = RQ_COLORMAP[indices]

    return Image.fromarray(image_array, 'RGBA')
