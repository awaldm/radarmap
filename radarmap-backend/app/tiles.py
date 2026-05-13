"""
Tiling operations.

We receive x, y, z (slippy map coordinates) relating to the Web Mercator World Grid.
"""

from PIL import Image
import numpy as np
import math
from pyproj import Proj, Transformer
from app import georef

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
    
    The return is lat/lon for these two points.
    """
    lat1, lon1 = num2deg(x, y, z)
    lat2, lon2 = num2deg(x + 1, y + 1, z)
    return (lon1, lat2, lon2, lat1)

def get_rq_colormap():
    """
    Creates a colormap for RQ product (Precipitation Intensity).
    Returns an array of shape (2501, 4) mapping values (scaled by 10) to RGBA.
    """
    # Max value is 250 (nodata), scaled by 10 it's 2500
    cmap = np.zeros((2501, 4), dtype=np.uint8)
    
    # Thresholds in mm/h
    thresholds = [0.1, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0]
    colors = [
        (0, 255, 0, 100),   # < 0.1: Light Green (applied only if > 0)
        (0, 200, 0, 120),   # 0.1 - 1.0: Green
        (0, 150, 0, 140),   # 1.0 - 2.5: Dark Green
        (255, 255, 0, 160), # 2.5 - 5.0: Yellow
        (255, 204, 0, 180), # 5.0 - 10.0: Orange
        (255, 102, 0, 200), # 10.0 - 25.0: Red-Orange
        (255, 0, 0, 220),   # 25.0 - 50.0: Red
        (153, 0, 76, 255)   # > 50.0: Magenta
    ]
    
    # Fill cmap based on scaled values (mm/h * 10)
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

def render_tile(data, tile_bounds, product="RQ", flags=None):
    """
    Render the tiles. 
    """

    # Unpack the tile bounds
    lon_min, lat_min, lon_max, lat_max = tile_bounds
    
    # Create a grid of pixel coordinates in the tile. We default to 256x256
    # TODO: this is probably the expensive part, and render_tile is called on every single request. Should investigate
    px, py = np.meshgrid(np.arange(256), np.arange(256))
    
    # Map pixel coordinates to lon/lat
    lon = lon_min + (lon_max - lon_min) * px / 255.0
    lat = lat_max - (lat_max - lat_min) * py / 255.0

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
    image_array = np.zeros((256, 256, 4), dtype=np.uint8)

    if product.upper() == "RE":
        # RE product: Precipitation Type
        # This one is a bit more complex to vectorize fully due to hail flags
        # But we can still do a lot
        
        # Get values for valid pixels
        vals = data[i_indices[valid_mask], j_indices[valid_mask]]
        
        # Base colors (Blue to White gradient for 0.0 to 1.0)
        # val = max(0.0, min(1.0, value))
        # r = int(255 * val); g = int(255 * val); b = 255; a = int(150 + (50 * val))
        v_clipped = np.clip(vals, 0.0, 1.0)
        r = (255 * v_clipped).astype(np.uint8)
        g = r
        b = np.full_like(r, 255)
        a = (150 + 50 * v_clipped).astype(np.uint8)
        
        colors = np.stack([r, g, b, a], axis=-1)
        
        # Apply Hail flag if available
        if flags is not None:
            f_vals = flags[i_indices[valid_mask], j_indices[valid_mask]]
            hail_mask = (f_vals & 1).astype(bool)
            colors[hail_mask] = [255, 0, 255, 200] # Magenta for Hail
            
        # Clear colors for values > 1.0 (nodata/invalid)
        invalid_val_mask = vals > 1.0
        colors[invalid_val_mask] = [0, 0, 0, 0]
        
        image_array[valid_mask] = colors
        
    else:
        # RQ product: Precipitation Intensity
        # Use pre-calculated colormap for fast lookup
        vals = data[i_indices[valid_mask], j_indices[valid_mask]]
        
        # Scale to indices (0 to 2500)
        indices = np.clip(np.round(vals * 10), 0, 2500).astype(int)
        
        image_array[valid_mask] = RQ_COLORMAP[indices]

    return Image.fromarray(image_array, 'RGBA')
