import structlog
import logging
import sys

from app.metrics import TILE_RENDER_TIME, DATA_ACQUISITION_TIME, CACHE_OPS_TOTAL, ACTIVE_REQUESTS

def prometheus_processor(logger, method_name, event_dict):
    \"\"\"
    A structlog processor that 'grafts' log events into Prometheus metrics.
    \"\"\"
    event = event_dict.get("event")
    
    if event == "tile_requested":
        TILE_RENDER_TIME.labels(
            product=event_dict.get("product", "UNKNOWN"),
            size=str(event_dict.get("size", "256"))
        ).observe(event_dict.get("duration_render", 0))
        
    elif event == "cache_hit":
        CACHE_OPS_TOTAL.labels(
            op="hit",
            type=event_dict.get("type", "unknown"),
            product=event_dict.get("product", "unknown")
        ).inc()
        
    elif event == "data_acquired":
        DATA_ACQUISITION_TIME.labels(
            product="RE" if "RE" in event_dict.get("filename", "") else "RQ",
            type="fetch"
        ).observe(event_dict.get("duration_total", 0))

    return event_dict

def setup_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            prometheus_processor, # The Graft!
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

logger = structlog.get_logger()
