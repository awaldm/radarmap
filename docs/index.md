# Radarmap

Radarmap is an experimental radar tile renderer for German Weather Service
(DWD) open radar data. The project is used to explore data acquisition,
georeferencing, tile rendering, telemetry, and CPU/GPU performance tradeoffs for
near-real-time precipitation visualization.

The repository contains:

- a FastAPI backend for fetching, parsing, caching, and rendering radar data
- a React frontend for map-based visualization
- CPU and CUDA rendering paths for comparing implementation strategies
- benchmark and telemetry code for measuring where request time is spent
- local-data and cache directories that are intentionally kept out of Git

This is not packaged as production software. The codebase is primarily a
working environment for testing rendering approaches and documenting the
results.

## Repository Layout

| Path | Purpose |
| :--- | :--- |
| `radarmap-backend/` | FastAPI backend, parser, renderers, services, tests. |
| `radarmap-frontend/` | React/Leaflet frontend. |
| `benchmarks/` | CPU/GPU benchmark sweep, GPU transfer helper, and benchmark CSV. |
| `scripts/` | Utility scripts such as DWD sample download helpers. |
| `data/` | Local DWD archives, ignored by Git except `data/README.md`. |
| `docs/` | Project documentation and generated images. |

## Documentation

- [Architecture](architecture.md): backend structure, renderer selection, and
  data flow
- [Rendering Pipeline](rendering.md): the steps involved in turning radar data
  into map tiles
- [Performance](performance.md): benchmark setup and current CPU/GPU
  measurements
- [Observability & Telemetry](telemetry.md): structured logging and Prometheus
  metrics
- [Project Structure Diagram](architecture_diagram.md): visual overview of the
  main components

## Current Focus

The current implementation renders PNG tiles from DWD radar composites. The CPU
path uses NumPy and PyProj. The CUDA path uses Numba kernels for projection and
sampling work.

The main open question is where to draw the line between server-side rendering
and client-side rendering. PNG tiles are easy to serve and inspect, but PNG
encoding becomes a significant part of request latency once the projection work
is moved to the GPU. A future version may expose raw or lightly encoded radar
buffers and perform more rendering work in the browser.
