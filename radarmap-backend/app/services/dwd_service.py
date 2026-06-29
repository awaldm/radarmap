"""
DWD data retrieval service.
Supports RE (RADVOR), RS (Composite), and legacy products.
"""

import io
import os
import re
import tarfile
import time
from pathlib import Path

import diskcache
import numpy as np
import requests
from fastapi import HTTPException

from app.config import settings
from app.logger import get_logger
from app.metrics import CACHE_OPS_TOTAL, DATA_ACQUISITION_TIME
from app.parser import parse_radolan_composite

logger = get_logger()

HDF5_PRODUCTS = {"RS", "RV"}


def _normalize_hdf5_timestamp(timestamp: str) -> str:
    compact = timestamp.replace("_", "")
    if len(compact) == 10:
        compact = f"20{compact}"
    if len(compact) == 12:
        return f"{compact[:8]}_{compact[8:]}"
    return timestamp


def _rv_archive_timestamp(timestamp: str) -> str:
    normalized = _normalize_hdf5_timestamp(timestamp)
    return f"{normalized[2:8]}{normalized[9:]}"


class DWDService:
    """
    DWD data retrieval.
    """

    def __init__(self):
        self.base_url = settings.DWD_BASE_URL
        self.cache = diskcache.Cache(settings.CACHE_DIR)
        self.ttl = settings.DATA_CACHE_TTL
        self.data_dir = settings.data_dir_path
        self.files_downloaded = 0
        self.total_mb_downloaded = 0.0
        self.cache_hits = 0
        self.cache_misses = 0

    def get_stats(self) -> dict:
        """
        Return the telemetry stats dictionary.
        """
        return {
            "files_downloaded": self.files_downloaded,
            "total_mb_downloaded": self.total_mb_downloaded,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
        }

    def _product_url(self, product: str) -> str:
        if product in HDF5_PRODUCTS:
            return f"{self.base_url}/composite/{product.lower()}/"
        if product == "RE":
            return f"{self.base_url}/radvor/re/"
        return f"{self.base_url}/radvor/{product.lower()}/"

    def _archive_filename(self, product: str, timestamp: str) -> str:
        if product == "RS":
            return f"composite_rs_{_normalize_hdf5_timestamp(timestamp)}.tar"
        if product == "RV":
            return f"DE1200_RV{_rv_archive_timestamp(timestamp)}.tar.bz2"
        return f"{product}{timestamp}.gz"

    def _archive_path(self, product: str, timestamp: str) -> Path:
        return self.data_dir / product.lower() / self._archive_filename(product, timestamp)

    def _archive_payload(self, product: str, timestamp: str, content: bytes) -> Path:
        path = self._archive_path(product, timestamp)
        if path.exists():
            return path

        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with open(temp_path, "wb") as f:
            f.write(content)
        os.replace(temp_path, path)
        logger.info("archived_dwd_file", product=product, path=str(path))
        return path

    def _extract_hdf5_analysis(self, product: str, timestamp: str, archive_content: bytes) -> bytes:
        normalized_timestamp = _normalize_hdf5_timestamp(timestamp)
        target_name = f"composite_{product.lower()}_{normalized_timestamp}_000-hd5"
        with tarfile.open(fileobj=io.BytesIO(archive_content), mode="r:*") as tar:
            try:
                member = tar.getmember(target_name)
            except KeyError:
                member = tar.getmembers()[0]

            extracted = tar.extractfile(member)
            if extracted is None:
                msg = f"Could not extract {member.name} from {product} archive."
                raise ValueError(msg)
            return extracted.read()

    def _load_local_file(self, product: str, timestamp: str) -> bytes | None:
        local_path = self._archive_path(product, timestamp)
        if not local_path.exists():
            return None

        logger.info("loading_local_file", product=product, path=str(local_path))
        with open(local_path, "rb") as f:
            archive_content = f.read()

        if product in HDF5_PRODUCTS:
            return self._extract_hdf5_analysis(product, timestamp, archive_content)
        return archive_content

    def _download_and_archive(self, product: str, timestamp: str) -> bytes:
        filename = self._archive_filename(product, timestamp)
        file_url = f"{self._product_url(product)}{filename}"
        response = requests.get(file_url, timeout=15)
        response.raise_for_status()

        self.files_downloaded += 1
        self.total_mb_downloaded += len(response.content) / (1024.0 * 1024.0)

        self._archive_payload(product, timestamp, response.content)

        if product in HDF5_PRODUCTS:
            return self._extract_hdf5_analysis(product, timestamp, response.content)
        return response.content

    def _timestamps_from_filenames(self, product: str, filenames: list[str]) -> list[str]:
        timestamps = []
        for filename in filenames:
            if product == "RS":
                match = re.search(r"composite_rs_(\d{8}_\d{4})\.tar", filename, re.IGNORECASE)
                if match:
                    timestamps.append(match.group(1))
            elif product == "RV":
                match = re.search(r"DE1200_RV(\d{10})\.tar\.bz2", filename, re.IGNORECASE)
                if match:
                    timestamps.append(_normalize_hdf5_timestamp(match.group(1)))
            else:
                match = re.search(
                    rf"{product}(\d{{10}}_\d{{3}})\.gz",
                    filename,
                    re.IGNORECASE,
                )
                if match:
                    timestamps.append(match.group(1))
        return timestamps

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
            self.cache_hits += 1
            # Count in prometheus
            CACHE_OPS_TOTAL.labels(op="hit", type="timestamps", product=product).inc()
            logger.info(
                "cache_hit",
                type="timestamps",
                product=product,
                duration=round(time.perf_counter() - start_time, 4),
            )
            return cached_ts

        # If desired timestamp is not in cache, check local data and/or the DWD server
        self.cache_misses += 1

        local_timestamps = []
        try:
            local_dir = self.data_dir / product.lower()
            if os.path.isdir(local_dir):
                local_timestamps = self._timestamps_from_filenames(product, os.listdir(local_dir))
        except Exception as le:
            logger.error("local_timestamps_scan_failed", product=product, error=str(le))

        try:
            url = self._product_url(product)
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            filenames = re.findall(r'href="([^"]+)"', response.text, re.IGNORECASE)
            timestamps = sorted(
                list(set(self._timestamps_from_filenames(product, filenames) + local_timestamps)),
                reverse=True,
            )
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
            if local_timestamps:
                return sorted(list(set(local_timestamps)), reverse=True)
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
            self.cache_hits += 1
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
        self.cache_misses += 1
        try:
            file_content = self._load_local_file(product, timestamp)
            if file_content is None:
                file_content = self._download_and_archive(product, timestamp)

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
