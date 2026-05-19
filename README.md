# Radarmap

A visualization application for RADVOR radar open data by the German Weather Service (DWD). This is not affiliated with DWD in any way.

## Overview

Radarmap is designed to provide smooth, low-latency access to precipitation intensity (RQ) and type (RE) forecast data. It leverages a modern stack to handle heavy coordinate transformations and tile rendering efficiently.

This is not production software in any way. This is mostly a playground for me to check out tileservers as backends, take them apart and profile them.

## Project Structure

- `radarmap-backend/`: FastAPI server responsible for data parsing, georeferencing, and tile rendering. 
- `radarmap-frontend/`: React application providing the map interface and timeline visualization. Currently still porting that one.

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
