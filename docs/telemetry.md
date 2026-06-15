# Observability and Telemetry

Radarmap uses structured logging for request diagnostics and derives a small set
of Prometheus metrics from selected log events.

The implementation is intentionally narrow: logs retain request context, while
metrics keep only low-cardinality fields that are useful for aggregation.

## Logging Pipeline

Logging is configured in `app/logger.py` with `structlog`.

The backend emits named events such as:

| Event | Emitted by | Purpose |
| :--- | :--- | :--- |
| `backend_startup` | application lifespan | Records process startup. |
| `backend_shutdown` | application lifespan | Records process shutdown. |
| `tile_requested` | tile endpoint | Records tile size, renderer, mode, and timing fields. |
| `tile_render_failed` | tile endpoint | Records tile render failures. |
| `cache_hit` | DWD service | Records cache hits for timestamps or radar data. |
| `data_acquired` | DWD service | Records time spent fetching and parsing data. |

The tile endpoint records these timing fields:

| Field | Meaning |
| :--- | :--- |
| `duration_total` | Full request time measured by the endpoint. |
| `duration_data` | Time spent retrieving parsed radar data. |
| `duration_render` | Time spent in tile bounds calculation and renderer execution. |
| `duration_serialize` | Time spent writing the PNG image. |

## Prometheus Metrics

`app/metrics.py` defines a dedicated Prometheus registry and the metrics exposed
through `/metrics`.

| Metric | Type | Labels | Description |
| :--- | :--- | :--- | :--- |
| `radarmap_total_requests_count` | Counter | none | Number of tile requests observed by the logging processor. |
| `radarmap_tile_render_seconds` | Histogram | `product`, `size` | Render duration from `tile_requested` events. |
| `radarmap_data_acquisition_seconds` | Histogram | `product`, `type` | Time spent acquiring radar data. |
| `radarmap_cache_ops_total` | Counter | `op`, `type`, `product` | Cache hit/miss accounting. |
| `radarmap_active_requests` | Gauge | none | Requests currently being processed. |

Implementation note: `radarmap_tile_render_seconds` has a `product` label, but
the current `tile_requested` log event does not include `product`. Until that
field is added to the event, the metric uses the default `UNKNOWN` label value
for product-level render timing.

## Cardinality Rules

Prometheus labels should remain bounded. Product, size, operation type, and
cache data type are acceptable labels because they have a small number of
possible values.

Tile coordinates should stay in logs rather than metrics. Adding `x` and `y` as
labels would create a large number of time series and make the metrics harder to
store and query.

## Reading Histograms

Prometheus histograms create related series:

| Suffix | Meaning |
| :--- | :--- |
| `_bucket` | Cumulative bucket counts used for latency percentiles. |
| `_sum` | Total observed duration. |
| `_count` | Number of observations. |
| `_created` | Metric creation timestamp. |

Average latency can be approximated as `_sum / _count`, but percentiles should
be computed from buckets.

## Useful Diagnostics

The current metrics are enough to separate several common cases:

| Symptom | Signals to check |
| :--- | :--- |
| Slow tile rendering | `duration_render`, `radarmap_tile_render_seconds`, tile `size`, selected `renderer`. |
| Slow cache misses | `duration_data`, `radarmap_data_acquisition_seconds`. |
| Cache behavior | `radarmap_cache_ops_total` by `op`, `type`, and `product`. |
| Concurrent load | `radarmap_active_requests` and request latency distribution. |
| PNG overhead | `duration_serialize` in structured logs. |

`duration_serialize` is currently logged but not exported as a Prometheus
metric. Add a separate histogram if PNG serialization needs dashboard-level
tracking.
