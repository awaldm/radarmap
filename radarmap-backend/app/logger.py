"""
Logging setup. This involves structlog to convert our logging messages to a standardized dict-like format.

structlog captures logger messages as dicts, it exposes arguments like (zoom=...) that are then
used to create event_dict dictionaries. This adds semantic meaning to logging messages. prometheus_processor then
handles each event and passes whatever happened to the correct prometheus metric.
"""

import structlog
import logging
import sys
from app.metrics import TILE_RENDER_TIME, DATA_ACQUISITION_TIME, CACHE_OPS_TOTAL, TOTAL_REQUESTS

def prometheus_processor(logger, method_name, event_dict):
    """
    Intercepts structured log events and updates Prometheus metrics.

    event_dict gets fed into Prometheus metrics via labels. The event_dict keys help differentiate semantically.


    """
    event = event_dict.get("event")

    if event == "tile_requested":
        TOTAL_REQUESTS.inc()
        TILE_RENDER_TIME.labels(
            product=event_dict.get("product", "UNKNOWN"),
            size=str(event_dict.get("size", "256"))
        ).observe(event_dict.get("duration_render", 0))
        # Note: we are not adding serialization to Prometheus yet to avoid bloating the registry
        
    elif event == "cache_hit":
        CACHE_OPS_TOTAL.labels(
            op="hit",
            type=event_dict.get("type", "unknown"),
            product=event_dict.get("product", "unknown")
        ).inc()
        
    elif event == "data_acquired":
        # Product detection from filename
        filename = event_dict.get("filename", "")
        product = "RE" if "RE" in filename else ("RQ" if "RQ" in filename else "UNKNOWN")
        
        DATA_ACQUISITION_TIME.labels(
            product=product,
            type="fetch"
        ).observe(event_dict.get("duration_total", 0))

    return event_dict


def setup_logging():
    """
    Set up structlog and the processors. These define a pipeline all logger commands get passed through

    The processor converts inputs like:
     logger.info("cache_hit", type="timestamps", product=product, duration=round(time.perf_counter() - start_time, 4))
    to outputs like
    2026-05-18 08:44:47 [info     ] cache_hit                      duration=0.0145 product=RE type=radar_data

    This is done by passing the keys 
    
    This gets called in main once.
    """
    structlog.reset_defaults()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            prometheus_processor,
            structlog.dev.ConsoleRenderer() # could be JSONRenderer() for file output
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )

def get_logger():
    """
    Return the structlog logger. Call this function in every module that intends to log anything.
    """
    return structlog.get_logger()
