import math
import time

import numpy as np
from numba import cuda, float32, uint8
from PIL import Image

from app.renderers.base import RenderingProvider
from app.tiles import RQ_COLORMAP, logger

# --- CUDA KERNELS ---


@cuda.jit
def nearest_neighbor_kernel(
    data, output, lon_min, lat_min, lon_max, lat_max, size, cmap, rows, cols, is_re, flags
):
    x, y = cuda.grid(2)
    if x >= size or y >= size:
        return

    # 1. Pixel -> Lon/Lat
    lon = lon_min + (lon_max - lon_min) * x / (size - 1)
    lat = lat_max - (lat_max - lat_min) * y / (size - 1)

    # 2. Polar Stereographic Projection
    RE_VAL, LON_0 = 6370040.0, 10.0
    lat_rad = lat * math.pi / 180.0
    lon_rad = (lon - LON_0) * math.pi / 180.0
    m = math.cos(lat_rad) / (1.0 + math.sin(lat_rad))
    rho = RE_VAL * m
    x_rad = rho * math.sin(lon_rad)
    y_rad = -rho * math.cos(lon_rad)

    # 3. Indexing
    x0, y0 = -523462.2, -4658645.0
    j = int(math.floor((x_rad - x0) / 1000.0))
    i = int(math.floor((y_rad - y0) / 1000.0))

    if 0 <= i < rows and 0 <= j < cols:
        val = data[i, j]
        if is_re:
            v_clipped = min(1.0, max(0.0, float(val)))
            c = uint8(255 * v_clipped)
            output[y, x, 0] = c  # R
            output[y, x, 1] = c  # G
            output[y, x, 2] = 255  # B
            output[y, x, 3] = uint8(150 + 50 * v_clipped)  # A
            if flags is not None and (flags[i, j] & 1):
                output[y, x, 0] = 255
                output[y, x, 1] = 0
                output[y, x, 2] = 255
                output[y, x, 3] = 200
        else:
            idx = int(round(val * 10))
            if idx < 0:
                idx = 0
            if idx > 2500:
                idx = 2500
            for k in range(4):
                output[y, x, k] = cmap[idx, k]
    else:
        for k in range(4):
            output[y, x, k] = 0


@cuda.jit
def bilinear_kernel(data, output, lon_min, lat_min, lon_max, lat_max, size, cmap, rows, cols):
    x, y = cuda.grid(2)
    if x >= size or y >= size:
        return

    lon = lon_min + (lon_max - lon_min) * x / (size - 1)
    lat = lat_max - (lat_max - lat_min) * y / (size - 1)

    RE_VAL, LON_0 = 6370040.0, 10.0
    lat_rad = lat * math.pi / 180.0
    lon_rad = (lon - LON_0) * math.pi / 180.0
    m = math.cos(lat_rad) / (1.0 + math.sin(lat_rad))
    rho = RE_VAL * m
    x_rad = rho * math.sin(lon_rad)
    y_rad = -rho * math.cos(lon_rad)

    x0, y0 = -523462.2, -4658645.0
    fj = (x_rad - x0) / 1000.0
    fi = (y_rad - y0) / 1000.0

    i0 = int(math.floor(fi))
    j0 = int(math.floor(fj))
    i1, j1 = i0 + 1, j0 + 1

    if 0 <= i0 < (rows - 1) and 0 <= j0 < (cols - 1):
        di, dj = float32(fi - i0), float32(fj - j0)
        v00, v01 = data[i0, j0], data[i0, j1]
        v10, v11 = data[i1, j0], data[i1, j1]

        val = (
            v00 * (1.0 - di) * (1.0 - dj)
            + v01 * (1.0 - di) * dj
            + v10 * di * (1.0 - dj)
            + v11 * di * dj
        )

        idx = int(round(val * 10))
        if idx < 0:
            idx = 0
        if idx > 2500:
            idx = 2500
        for k in range(4):
            output[y, x, k] = cmap[idx, k]
    else:
        for k in range(4):
            output[y, x, k] = 0


class CudaRenderer(RenderingProvider):
    def __init__(self):
        self.cmap_gpu = cuda.to_device(RQ_COLORMAP)

    def render(
        self,
        data: np.ndarray,
        tile_bounds: tuple,
        product: str,
        flags: np.ndarray,
        size: int,
        interpolation: str = "nearest",
    ) -> Image.Image:
        t_start = time.perf_counter()
        # Prepare radar and flags data
        rows, cols = data.shape
        data_gpu = cuda.to_device(data.astype(np.float32))

        # Numba kernels can't handle None for array arguments easily.
        # If no flags, pass a tiny dummy array.
        if flags is not None:
            flags_gpu = cuda.to_device(flags)
        else:
            flags_gpu = cuda.to_device(np.zeros((1, 1), dtype=np.uint8))

        output_gpu = cuda.device_array((size, size, 4), dtype=np.uint8)

        threadsperblock = (16, 16)
        blockspergrid = (math.ceil(size / 16), math.ceil(size / 16))
        lon_min, lat_min, lon_max, lat_max = tile_bounds

        if interpolation == "bilinear" and product.upper() != "RE":
            bilinear_kernel[blockspergrid, threadsperblock](
                data_gpu,
                output_gpu,
                lon_min,
                lat_min,
                lon_max,
                lat_max,
                size,
                self.cmap_gpu,
                rows,
                cols,
            )
        else:
            is_re = product.upper() == "RE"
            nearest_neighbor_kernel[blockspergrid, threadsperblock](
                data_gpu,
                output_gpu,
                lon_min,
                lat_min,
                lon_max,
                lat_max,
                size,
                self.cmap_gpu,
                rows,
                cols,
                is_re,
                flags_gpu,
            )

        res = Image.fromarray(output_gpu.copy_to_host(), "RGBA")
        logger.debug(
            "render_microbench",
            duration=round(time.perf_counter() - t_start, 4),
            size=size,
            provider="numba",
        )
        return res
