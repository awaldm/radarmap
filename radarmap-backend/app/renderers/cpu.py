import time

import numpy as np
from PIL import Image

from app.renderers.base import RenderingProvider
from app.tiles import RQ_COLORMAP, logger, transformer_wgs84_to_radolan


class NumpyRenderer(RenderingProvider):
    def render(
        self,
        data: np.ndarray,
        tile_bounds: tuple,
        product: str,
        flags: np.ndarray,
        size: int,
        interpolation: str,
    ) -> Image.Image:
        """
        Standard NumPy-based CPU rendering path.
        """
        lon_min, lat_min, lon_max, lat_max = tile_bounds
        rows, cols = data.shape
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

        # 3. Index Calculation
        t_idx_start = time.perf_counter()
        x0, y0 = -523462.2, -4658645.0
        fj = (x_rad - x0) / 1000.0
        fi = (y_rad - y0) / 1000.0

        margin = 1 if interpolation == "bilinear" else 0
        valid_mask = (fi >= 0) & (fi < (rows - margin)) & (fj >= 0) & (fj < (cols - margin))
        t_idx = time.perf_counter() - t_idx_start

        # 4. Data Sampling & Colormapping
        t_cmap_start = time.perf_counter()
        image_array = np.zeros((size, size, 4), dtype=np.uint8)

        if interpolation == "bilinear" and product.upper() != "RE":
            i0 = np.floor(fi[valid_mask]).astype(int)
            i1 = i0 + 1
            j0 = np.floor(fj[valid_mask]).astype(int)
            j1 = j0 + 1
            di, dj = fi[valid_mask] - i0, fj[valid_mask] - j0

            v00, v01 = data[i0, j0], data[i0, j1]
            v10, v11 = data[i1, j0], data[i1, j1]

            vals = (
                v00 * (1 - di) * (1 - dj)
                + v01 * (1 - di) * dj
                + v10 * di * (1 - dj)
                + v11 * di * dj
            )
        else:
            vals = data[np.floor(fi[valid_mask]).astype(int), np.floor(fj[valid_mask]).astype(int)]

        if product.upper() == "RE":
            v_clipped = np.clip(vals, 0.0, 1.0)
            r = g = (255 * v_clipped).astype(np.uint8)
            b = np.full_like(r, 255)
            a = (150 + 50 * v_clipped).astype(np.uint8)
            colors = np.stack([r, g, b, a], axis=-1)
            if flags is not None:
                f_idx_i = np.floor(fi[valid_mask]).astype(int)
                f_idx_j = np.floor(fj[valid_mask]).astype(int)
                f_vals = flags[f_idx_i, f_idx_j]
                colors[(f_vals & 1).astype(bool)] = [255, 0, 255, 200]
            image_array[valid_mask] = colors
        else:
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
            size=size,
            provider="numpy",
        )

        return Image.fromarray(image_array, "RGBA")
