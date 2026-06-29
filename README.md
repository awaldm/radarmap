# Radarmap

Radarmap is an inspectable radar-map pipeline for [German Weather Service (DWD) RADVOR radar open data](https://opendata.dwd.de/weather/radar/radvor/). It parses meteorological grid files, projects them from polar stereographic coordinates to web-map coordinates, renders interactive map tiles, and exposes tile-rendering performance metrics.

This project is an engineering study and benchmark, not a generic map dashboard. The primary goal is comparing CPU and server-side GPU rendering for a high-resolution tile path to examine when GPU transfer overhead is worth paying.

---

## 1. System Architecture

```mermaid
graph TD
    subgraph DWD Open Data
        DWD[opendata.dwd.de]
    end

    subgraph Backend (FastAPI + CuPy/NumPy)
        Srv[dwd_service] -->|Cache Check| Cache[(diskcache)]
        Srv -->|Cache Miss| DWD
        Parse[parser.py] -->|Decompress & Decode| Srv
        
        subgraph Tile Renderers
            CPU[NumpyRenderer]
            GPU[CudaRenderer]
        end
        
        Parse --> CPU
        Parse --> GPU
    end

    subgraph Frontend (React + Leaflet)
        UI[React App] -->|Request Tiles| BackendAPI[FastAPI Tiles Endpoint]
        BackendAPI --> CPU
        BackendAPI --> GPU
        UI -->|Fetch Metrics| Prom[Prometheus Endpoint]
        UI -->|Telemetry Stats| StatsAPI[FastAPI Stats Endpoint]
    end
```

---

## 2. Performance Benchmarks

Below is a comparison of tile-rendering latency on a local benchmarking run, comparing the standard Python CPU (`NumPy`) path against the parallelized GPU (`Numba CUDA`) path:

| Tile Size (px) | Interpolation | CPU (NumPy) Latency | GPU (Numba CUDA) Latency | Speedup Factor |
| :--- | :--- | :--- | :--- | :--- |
| **256** | Nearest | 12.56 ms | 8.74 ms | **1.4x** |
| **256** | Bilinear | 12.89 ms | 8.32 ms | **1.5x** |
| **512** | Nearest | 33.71 ms | 12.44 ms | **2.7x** |
| **512** | Bilinear | 34.55 ms | 13.83 ms | **2.5x** |
| **1024** | Nearest | 113.00 ms | 27.73 ms | **4.1x** |
| **1024** | Bilinear | 123.96 ms | 27.51 ms | **4.5x** |
| **2048** | Nearest | 436.22 ms | 81.69 ms | **5.3x** |
| **2048** | Bilinear | 473.87 ms | 81.69 ms | **5.8x** |

> [!NOTE]  
> The speedup scales with tile resolution because the overhead of transferring the 900x900 grid memory to the GPU is constant, while the computing parallelization benefits increase quadratically.

---

## 3. What This Does

I built this to handle several types of radar data, and conduct fast coordinate mapping on CPU and GPU. The backend is instrumented via prometheus and structlog, adding a layer of observability that makes benchmarking a bit easier.

---

## 5. Getting Started

### Prerequisites

* Python >= 3.10
* Node.js >= 18
* `uv` (Fast Python dependency installer)

### Running Locally

You can launch both services together from the frontend directory:

1. **Setup Backend Dependencies**:
   ```bash
   cd radarmap-backend
   uv sync
   ```
2. **Setup Frontend Dependencies**:
   ```bash
   cd ../radarmap-frontend
   npm install
   ```
3. **Run Dev Environment**:
   ```bash
   npm run dev
   ```
   This will simultaneously spin up the frontend on `http://localhost:5173` and the backend on `http://localhost:8000`.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
