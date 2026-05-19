"""
The prometheus metrics that are being collected by the process. These define labels that
can be used by our structlog processor to pass logger message contents along to prometheus.
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

# Create an EXPLICIT registry to avoid global state confusion
REGISTRY = CollectorRegistry()

# Diagnostic Counter (No labels)
TOTAL_REQUESTS = Counter(
    "radarmap_total_requests_count",
    "Total number of tile requests received",
    registry=REGISTRY
)

# 1. Performance Metrics
TILE_RENDER_TIME = Histogram(
    "radarmap_tile_render_seconds",
    "Time spent rendering a tile (projection + colormap)",
    ["product", "size"],
    registry=REGISTRY,
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf"))
)

DATA_ACQUISITION_TIME = Histogram(
    "radarmap_data_acquisition_seconds",
    "Time spent acquiring radar data (cache/download/parse)",
    ["product", "type"],
    registry=REGISTRY
)

# 2. Operational Metrics
CACHE_OPS_TOTAL = Counter(
    "radarmap_cache_ops_total",
    "Total number of cache operations",
    ["op", "type", "product"],
    registry=REGISTRY
)

ACTIVE_REQUESTS = Gauge(
    "radarmap_active_requests",
    "Number of currently processing tile requests",
    registry=REGISTRY
)
