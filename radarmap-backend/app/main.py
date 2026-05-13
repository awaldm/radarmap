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

@app.get("/api/radvor/timestamps", response_model=List[str])
def get_available_timestamps(product: str = Query("RQ", regex="^(RQ|RE|rq|re)$")):
    return dwd_service.get_available_timestamps(product)

@app.get("/api/tiles/{z}/{x}/{y}.png")
def get_tile_endpoint(z: int, x: int, y: int, timestamp: str, product: str = "RQ"):

    # Get entire frame
    data, flags = dwd_service.get_radvor_data(timestamp, product)

    try:
        tile_bounds = get_tile_bounds(z, x, y)
        tile_image = render_tile(data, tile_bounds, product=product.upper(), flags=flags)
        
        buf = io.BytesIO()
        tile_image.save(buf, format='PNG')
        buf.seek(0)
        
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        print(f"Error rendering tile for {z}/{x}/{y} with timestamp {timestamp}: {e}")
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
