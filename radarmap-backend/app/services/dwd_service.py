"""
DWD data retrieval service.
Supports RE (RADVOR), RS (Composite), and legacy products.
"""

import io
import re
import tarfile
import time

import diskcache
import numpy as np
import requests
from fastapi import HTTPException

from app.config import settings
from app.logger import get_logger
from app.metrics import CACHE_OPS_TOTAL, DATA_ACQUISITION_TIME
from app.parser import parse_radolan_composite

logger = get_logger()


class DWDService:
    """
    DWD data retrieval.
    """

    def __init__(self):
        self.base_url = settings.DWD_BASE_URL
        self.cache = diskcache.Cache(settings.CACHE_DIR)
        self.ttl = settings.DATA_CACHE_TTL

    def get_available_timestamps(self, product: str) -> list[str]:
        """
        Obtain all available timestamps.

        This currently serves only the timestamps endpoint in main.py, not much else.
        """
        product = product.upper()  # RE, RS, etc.
        cache_key = f"timestamps_{product}"

        start_time = time.perf_counter()
        cached_ts = self.cache.get(cache_key)  # cached timestamp

        # Check if timestamp is in cache
        if cached_ts:
            # Count in prometheus
            CACHE_OPS_TOTAL.labels(op="hit", type="timestamps", product=product).inc()
            logger.info(
                "cache_hit",
                type="timestamps",
                product=product,
                duration=round(time.perf_counter() - start_time, 4),
            )
            return cached_ts

        # If desired timestamp is not in cache, check the DWD server
        try:
            if product == "RS":
                url = f"{self.base_url}/composite/rs/"
                pattern = r"composite_rs_(\d{8}_\d{4})\.tar"
            elif product == "RE":
                url = f"{self.base_url}/radvor/re/"
                pattern = r"RE(\d{10}_\d{3})\.gz"
            else:
                url = f"{self.base_url}/radvor/{product.lower()}/"
                pattern = f"{product}(\d{{10}}_\d{{3}})\.gz"

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            filenames = re.findall(pattern, response.text)  # All filenames in URL
            if not filenames:
                return []

            timestamps = sorted(list(set(filenames)), reverse=True)
            # Cache timestamps for 5 minutes
            self.cache.set(cache_key, timestamps, expire=300)
            logger.info(
                "fetched_timestamps",
                product=product,
                count=len(timestamps),
                duration=round(time.perf_counter() - start_time, 4),
            )
            return timestamps
        except Exception as e:
            logger.error("fetch_timestamps_failed", product=product, error=str(e))
            return []

    def get_radvor_data(
        self, timestamp: str, product: str = "RS"
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """
        Obtain the actual data.
        The timestamp string needs to be formatted in the way DWD stores it on the server.
        """
        product = product.upper()

        # Set up cache names for lookup
        cache_key = f"data_{product}_{timestamp}"

        start_time = time.perf_counter()
        cached_data = self.cache.get(cache_key)

        # If data already in cache -> success!
        if cached_data:
            # Count in prometheus
            CACHE_OPS_TOTAL.labels(op="hit", type="radar_data", product=product).inc()
            logger.info(
                "cache_hit",
                type="radar_data",
                product=product,
                timestamp=timestamp,
                duration=round(time.perf_counter() - start_time, 4),
            )
            return cached_data["values"], cached_data["flags"]

        # If not cached, actually get the data.
        try:
            if product == "RS":
                # The RS product is inside a TAR file
                file_url = f"{self.base_url}/composite/rs/composite_rs_{timestamp}.tar"
                response = requests.get(file_url, timeout=15)
                response.raise_for_status()

                # Extract the 000 frame (analysis) from the TAR
                with tarfile.open(fileobj=io.BytesIO(response.content)) as tar:
                    # Frame name format: composite_rs_20260601_0720_000-hd5
                    target_name = f"composite_rs_{timestamp}_000-hd5"
                    try:
                        member = tar.getmember(target_name)
                        file_content = tar.extractfile(member).read()
                    except KeyError:
                        # Fallback: just get the first member
                        file_content = tar.extractfile(tar.getmembers()[0]).read()
            else:
                target_filename = f"{product}{timestamp}.gz"
                url_path = "radvor/re" if product == "RE" else f"radvor/{product.lower()}"
                file_url = f"{self.base_url}/{url_path}/{target_filename}"
                response = requests.get(file_url, timeout=15)
                response.raise_for_status()
                file_content = response.content

            # Parse using the unified parser
            metadata, values, flags = parse_radolan_composite(file_content)

            total_time = time.perf_counter() - start_time
            DATA_ACQUISITION_TIME.labels(product=product, type="fetch").observe(total_time)

            # Cache the parsed data
            self.cache.set(cache_key, {"values": values, "flags": flags}, expire=self.ttl)
            logger.info(
                "data_acquired",
                product=product,
                timestamp=timestamp,
                duration_total=round(total_time, 4),
            )
            return values, flags

        except Exception as e:
            logger.error("data_acquisition_failed", product=product, ts=timestamp, error=str(e))
            raise HTTPException(
                status_code=404, detail=f"Could not fetch or parse data: {e}"
            ) from e


dwd_service = DWDService()
