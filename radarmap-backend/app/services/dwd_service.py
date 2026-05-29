"""
This contains most of the logic concerned with actually getting the data.
"""

import re
import time

import diskcache
import numpy as np
import requests
from fastapi import HTTPException

from app.config import settings
from app.logger import get_logger
from app.parser import parse_radolan_composite

logger = get_logger()


class DWDService:
    """
    DWD data retrieval.
    """

    def __init__(self):
        self.base_url = settings.DWD_RADVOR_BASE_URL
        self.cache = diskcache.Cache(settings.CACHE_DIR)
        self.ttl = settings.DATA_CACHE_TTL

    def get_available_timestamps(self, product: str) -> list[str]:
        """
        Obtain all available timestamps.
        """
        product = product.upper()
        cache_key = f"timestamps_{product}"

        start_time = time.perf_counter()
        cached_ts = self.cache.get(cache_key)

        if cached_ts:
            t = round(time.perf_counter() - start_time, 4)
            logger.info("cache_hit", type="timestamps", product=product, duration=t)
            return cached_ts

        try:
            url = f"{self.base_url}/{product.lower()}/"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            pattern = f"{product}(\d{{10}}_\d{{3}})\.gz"
            filenames = re.findall(pattern, response.text)

            if not filenames:
                return []

            timestamps = sorted(list(set(filenames)), reverse=True)
            self.cache.set(cache_key, timestamps, expire=300)
            t = round(time.perf_counter() - start_time, 4)
            logger.info("fetched_timestamps", product=product, count=len(timestamps), duration=t)
            return timestamps
        except Exception as e:
            logger.error("fetch_timestamps_failed", product=product, error=str(e))
            return []

    def get_radvor_data(
        self, timestamp: str, product: str = "RQ"
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """
        Obtain the actual data.
        """
        product = product.upper()
        cache_key = f"data_{product}_{timestamp}"

        start_time = time.perf_counter()
        cached_data = self.cache.get(cache_key)

        if cached_data:
            t = round(time.perf_counter() - start_time, 4)
            logger.info(
                "cache_hit",
                type="radar_data",
                product=product,
                timestamp=timestamp,
                duration=t,
            )
            return cached_data["values"], cached_data["flags"]

        target_filename = f"{product}{timestamp}.gz"
        file_url = f"{self.base_url}/{product.lower()}/{target_filename}"

        try:
            download_start = time.perf_counter()
            response = requests.get(file_url, timeout=15)
            response.raise_for_status()
            t_download = time.perf_counter() - download_start

            parse_start = time.perf_counter()
            metadata, values, flags = parse_radolan_composite(response.content)
            t_parse = time.perf_counter() - parse_start

            total_time = time.perf_counter() - start_time

            self.cache.set(cache_key, {"values": values, "flags": flags}, expire=self.ttl)
            logger.info(
                "data_acquired",
                filename=target_filename,
                duration_total=round(total_time, 4),
                duration_download=round(t_download, 4),
                duration_parse=round(t_parse, 4),
            )
            return values, flags
        except Exception as e:
            logger.error("data_acquisition_failed", filename=target_filename, error=str(e))
            raise HTTPException(status_code=404, detail="Could not fetch or parse data") from e


dwd_service = DWDService()
