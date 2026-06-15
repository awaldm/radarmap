# Architecture

Radarmap is organized around a small backend pipeline:

1. Fetch DWD radar products such as RS.
2. Parse the product into NumPy arrays and metadata.
3. Cache parsed data locally.
4. Render requested XYZ map tiles through a selected rendering provider.
5. Return PNG tiles to the frontend.

The design keeps data acquisition, parsing, rendering, and telemetry separate
enough that individual parts can be benchmarked or replaced.

## Backend Components

| Component | Responsibility |
| :--- | :--- |
| `app/services/dwd_service.py` | Fetches product listings and radar files from DWD open data endpoints. |
| `app/parser.py` | Parses RADOLAN/RADVOR-style products into arrays used by the renderer. |
| `diskcache` | Stores timestamp lists and parsed radar data to avoid repeated downloads and parsing. |
| `app/renderers/` | Contains interchangeable rendering implementations. |
| `app/main.py` | Defines the FastAPI endpoints and request-level timing. |
| `app/logger.py` | Converts selected structured log events into Prometheus metrics. |

## Rendering Providers

The backend exposes rendering through a shared `RenderingProvider` interface in
`app/renderers/base.py`. The current implementations are:

| Provider | File | Description |
| :--- | :--- | :--- |
| `numpy` | `app/renderers/cpu.py` | CPU path using NumPy and PyProj. |
| `numba` | `app/renderers/cuda.py` | CUDA path using Numba kernels. |

The tile endpoint selects the provider with a query parameter:

```text
GET /api/tiles/{z}/{x}/{y}.png?renderer=numpy
GET /api/tiles/{z}/{x}/{y}.png?renderer=numba
```

Renderer instances are loaded through `app/renderers/__init__.py`. The CUDA
renderer is lazy-loaded so CPU-only environments can still use the backend.

## Request Flow

A tile request follows this path:

1. The API receives `z`, `x`, `y`, `timestamp`, `product`, `size`,
   `renderer`, and `interpolation`.
2. `DwdService` returns the requested radar array and flags, using the local
   cache when available.
3. The API computes the geographic bounds for the XYZ tile.
4. The selected renderer projects tile pixels into the radar grid and produces
   an RGBA image.
5. The API serializes the image as PNG and streams it to the client.
6. Structured timing data is logged for observability.

## Existing Tile Server Options

Radarmap uses a custom FastAPI tile endpoint, but this is not the only possible
shape for the system.

| Option | Fit for Radarmap |
| :--- | :--- |
| [GeoServer](https://docs.geoserver.org/latest/en/user/services/wms/index.html) | Good fit for publishing configured raster layers through WMS/WMTS/WCS. More operational structure than needed for the current benchmark-oriented backend. |
| [TiTiler](https://developmentseed.org/titiler/) | Good fit for dynamic tiling from Cloud Optimized GeoTIFF, STAC, Zarr, and related raster formats. A closer fit if the DWD products are first converted into those formats. |
| MapServer | Mature option for OGC map services and GDAL-backed raster data, but less aligned with the current Python renderer comparison. |
| MapProxy | Useful as a proxy/cache in front of existing WMS/WMTS services. Less relevant while Radarmap is generating tiles directly from parsed radar arrays. |
| Vector tile servers | Good for vector data, MBTiles, or PostGIS-backed layers. Not a good match for per-pixel radar reprojection and colormapping. |

This implementation exists mainly for benchmarking and observability purposes.
It keeps DWD product parsing, array-level sampling, CPU/CUDA renderer selection,
and request timing in one small code path.

## Design Constraints

The backend is intentionally conservative in a few places:

- The CPU renderer remains the baseline because it is portable and easy to run
  in CI.
- The CUDA renderer is optional because it depends on compatible hardware,
  drivers, and Numba CUDA support.
- PNG output is retained because it works directly with standard map clients,
  even though it is not the lowest-latency transport format.
- Product handling is kept close to the DWD source format so changes in upstream
  products can be tested without hiding them behind a large abstraction.
