# Radarmap

A visualization application for [RADVOR radar open data](https://opendata.dwd.de/weather/radar/radvor/) by the German Weather Service (DWD). This is not affiliated with DWD in any way.



Radarmap is designed to provide smooth, low-latency access to precipitation intensity (RQ) and type (RE) radar forecast data. It employs a flexible stack to handle heavy coordinate transformations and tile rendering efficiently. It parses compact meteorological grid files, projects them into web-map coordinates, renders interactive map tiles, and records tile-rendering metrics.

This is mainly an engineering study, not a generic map demo. The current version server-side CPU and GPU rendering for high-resolution tiles and documents where the GPU transfer cost is worth paying.



## Overview


This is not production software in any way. This is mostly a playground for me to check out tileservers as backends, take them apart and profile them.

## Project Structure

- `radarmap-backend/`: FastAPI server responsible for data parsing, georeferencing, and tile rendering. 
- `radarmap-frontend/`: React application providing the map interface and timeline visualization.

## Performance & Scaling

Radarmap is built as a benchmarking platform. It features multiple render paths to compare CPU (NumPy) vs. GPU (Numba CUDA) rendering performance.

## Status

The Numba CUDA implementation reduced render time from about 880 ms to 80 ms. The important question is not the speedup alone, but what it says about the regime where server-side GPU rendering can overcome transfer/setup overhead.


## Getting Started

### Backend
1. Ensure you have `uv` installed.
2. `cd radarmap-backend`
3. `uv sync`
4. `uv run uvicorn app.main:app`

### Frontend
1. `cd radarmap-frontend`
2. `npm install`
3. `npm run dev`

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
