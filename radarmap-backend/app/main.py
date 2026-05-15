"""
The Radarmap backend main entry point.

"""
import io
import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from contextlib import asynccontextmanager
from typing import List

from app.tiles import get_tile_bounds, render_tile
from app.config import settings
from app.services.dwd_service import dwd_service
from app.schemas.models import MaxValueResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Any startup logic if needed
    yield
    # Any cleanup logic if needed

app = FastAPI(lifespan=lifespan, title="Radarmap API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.logger import setup_logging, logger

# Initialize structured logging
setup_logging()

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

@app.get("/api/radvor/timestamps", response_model=List[str])
def get_available_timestamps(product: str = Query("RQ", regex="^(RQ|RE|rq|re)$")):
    return dwd_service.get_available_timestamps(product)

@app.get("/api/tiles/{z}/{x}/{y}.png")
def get_tile_endpoint(z: int, x: int, y: int, timestamp: str, product: str = "RQ"):
    start_time = time.perf_counter()
    
    # Get entire frame
    data, flags = dwd_service.get_radvor_data(timestamp, product)
    data_time = time.perf_counter() - start_time

    try:
        render_start = time.perf_counter()
        tile_bounds = get_tile_bounds(z, x, y)
        tile_image = render_tile(data, tile_bounds, product=product.upper(), flags=flags)
        render_time = time.perf_counter() - render_start
        
        buf = io.BytesIO()
        tile_image.save(buf, format='PNG')
        buf.seek(0)
        
        total_time = time.perf_counter() - start_time
        logger.info(
            "tile_requested",
            z=z, x=x, y=y,
            product=product.upper(),
            duration_total=round(total_time, 4),
            duration_data=round(data_time, 4),
            duration_render=round(render_time, 4)
        )
        
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        logger.error("tile_render_failed", z=z, x=x, y=y, error=str(e))
        raise HTTPException(status_code=500, detail="Error generating tile.")

@app.get("/api/radvor/max-value", response_model=MaxValueResponse)
def get_max_value(timestamp: str, product: str = "RQ"):
    data, _ = dwd_service.get_radvor_data(timestamp, product)
    
    # Filter valid data based on product
    # RQ: < 250 is valid (intensity)
    # RE: <= 1.0 is valid (type)
    if product.upper() == "RE":
        valid_data = data[data <= 1.0]
    else:
        valid_data = data[data < 250]
        
    max_value = np.max(valid_data) if valid_data.size > 0 else 0.0
    return MaxValueResponse(max_value=float(max_value))

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
