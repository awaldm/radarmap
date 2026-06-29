"""
The Radarmap backend main entry point.
"""

import io
import time
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import StreamingResponse

from app.config import settings
from app.logger import get_logger, setup_logging
from app.metrics import ACTIVE_REQUESTS, REGISTRY
from app.renderers import get_renderer
from app.schemas.models import MaxValueResponse
from app.services.dwd_service import dwd_service
from app.tiles import get_tile_bounds

# 1. SETUP LOGGING FIRST THING (after imports per PEP8)
setup_logging()
logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("backend_startup", status="ok")
    yield
    logger.info("backend_shutdown")


app = FastAPI(lifespan=lifespan, title="Radarmap API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/metrics")
def metrics():
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/stats")
def get_stats():
    return dwd_service.get_stats()


@app.get("/api/radvor/timestamps", response_model=list[str])
def get_available_timestamps(product: str = Query("RQ", regex="^(RQ|RE|RS|RV|rq|re|rs|rv)$")):
    return dwd_service.get_available_timestamps(product)


@app.get("/api/tiles/{z}/{x}/{y}.png")
def get_tile_endpoint(
    z: int,
    x: int,
    y: int,
    timestamp: str,
    product: str = "RQ",
    size: int = 256,
    mode: str = "organic",
    renderer: str = "numpy",
    interpolation: str = "nearest",
):
    ACTIVE_REQUESTS.inc()
    start_time = time.perf_counter()

    try:
        # 1. Data Acquisition
        t_data_start = time.perf_counter()
        data, flags = dwd_service.get_radvor_data(timestamp, product)
        t_data = time.perf_counter() - t_data_start

        # 2. Rendering (Unified Factory)
        render_start = time.perf_counter()
        tile_bounds = get_tile_bounds(z, x, y)

        # Get the requested renderer (numpy, numba, etc.)
        engine = get_renderer(renderer)
        tile_image = engine.render(
            data,
            tile_bounds,
            product=product.upper(),
            flags=flags,
            size=size,
            interpolation=interpolation,
        )
        t_render = time.perf_counter() - render_start

        # 3. Serialization
        t_save_start = time.perf_counter()
        buf = io.BytesIO()
        tile_image.save(buf, format="PNG")
        buf.seek(0)
        t_save = time.perf_counter() - t_save_start

        total_time = time.perf_counter() - start_time

        # This log will trigger the Prometheus Graft in logger.py
        logger.info(
            "tile_requested",
            z=z,
            x=x,
            y=y,
            size=size,
            mode=mode,
            renderer=renderer,
            duration_total=round(total_time, 4),
            duration_render=round(t_render, 4),
            duration_data=round(t_data, 4),
            duration_serialize=round(t_save, 4),
        )

        return StreamingResponse(buf, media_type="image/png")

    except Exception as e:
        logger.error("tile_render_failed", z=z, x=x, y=y, error=str(e))
        raise HTTPException(status_code=500, detail="Error generating tile.") from e
    finally:
        ACTIVE_REQUESTS.dec()


@app.get("/api/radvor/max-value", response_model=MaxValueResponse)
def get_max_value(timestamp: str, product: str = "RQ"):
    data, _ = dwd_service.get_radvor_data(timestamp, product)
    if product.upper() == "RE":
        valid_data = data[data <= 1.0]
    else:
        valid_data = data[data < 250]
    max_value = np.max(valid_data) if valid_data.size > 0 else 0.0
    return MaxValueResponse(max_value=float(max_value))


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
