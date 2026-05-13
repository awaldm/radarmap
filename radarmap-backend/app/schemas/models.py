"""
The pydantic infra for this repo.
"""
from pydantic import BaseModel
from typing import List, Optional

class Stats(BaseModel):
    files_downloaded: int
    total_mb_downloaded: float
    cache_hits: int
    cache_misses: int

class MaxValueResponse(BaseModel):
    max_value: float

class TimestampsResponse(BaseModel):
    timestamps: List[str]
