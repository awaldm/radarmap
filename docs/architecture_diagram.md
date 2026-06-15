# Project Structure and Data Flow

This diagram shows the main runtime components involved in serving a radar
tile. It omits development scripts and benchmark-only files.

```mermaid
graph TD
    subgraph "DWD Open Data"
        DWD_TAR[RS product files]
        DWD_GZ[RE/RQ product files]
    end

    subgraph "Backend: FastAPI"
        Service[DWD service]
        Parser[Parser]
        Cache[(DiskCache)]
        API[Tile API]
        Factory[Renderer factory]

        subgraph "Renderers"
            CPU[NumPy/PyProj renderer]
            CUDA[Numba CUDA renderer]
        end

        Logger[Structured logs]
        Metrics[Prometheus metrics]
    end

    subgraph "Frontend"
        UI[React UI]
        Map[MapLibre/Deck.gl map]
    end

    DWD_TAR --> Service
    DWD_GZ --> Service
    Service --> Parser
    Parser --> Cache
    Cache --> API
    API --> Factory

    Factory -->|renderer=numpy| CPU
    Factory -->|renderer=numba| CUDA

    CPU -->|PNG tile| Map
    CUDA -->|PNG tile| Map
    UI --> Map

    API -.-> Logger
    Service -.-> Logger
    Logger -.-> Metrics
```

The backend is responsible for radar data access, parsing, caching, tile bounds,
renderer selection, and PNG serialization.

Both renderers use inverse mapping: each output pixel is mapped back into the
source radar grid. This avoids gaps in the output tile and makes CPU/GPU results
easier to compare.

Telemetry is derived from structured log events. Selected event fields are
converted into Prometheus counters, gauges, and histograms.
