"""
This contains most of the logic concerned with actually getting the data.
"""
import re
import requests
import gzip
import os
import datetime
from typing import List, Dict, Tuple, Optional
from fastapi import HTTPException
import numpy as np
import diskcache
from app.parser import parse_radolan_composite
from app.config import settings

class DWDService:
    """
    DWD data retrieval.
    """
    def __init__(self):
        self.base_url = settings.DWD_RADVOR_BASE_URL
        self.cache = diskcache.Cache(settings.CACHE_DIR)
        self.ttl = settings.DATA_CACHE_TTL
        
    def get_available_timestamps(self, product: str) -> List[str]:
        """
        Obtain all available timestamps.
        
        This currently serves only the timestamps endpoint in main.py, not much else.
        """
        product = product.upper() # RE or RQ
        cache_key = f"timestamps_{product}"
        cached_ts = self.cache.get(cache_key) # cached timestamp
        
        # Check if timestamp is in cache
        if cached_ts:
            return cached_ts

        # If desired timestamp is not in cache, check the DWD server
        try:
            url = f"{self.base_url}/{product.lower()}/"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # Match href="RQ1234567890_123.gz"
            pattern = f'href="{product}(\d{{10}}_\d{{3}})\.gz"'
            filenames = re.findall(pattern, response.text) # All filenames in URL
            
            if not filenames:
                return []
            
            timestamps = sorted(list(set(filenames)), reverse=True)
            # Cache timestamps for 5 minutes
            self.cache.set(cache_key, timestamps, expire=300)
            return timestamps
        except Exception as e:
            print(f"Error fetching timestamps: {e}")
            return []

    def get_radvor_data(self, timestamp: str, product: str = "RQ") -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Obtain the actual data.

        The timestamp string needs to be formatted in the way DWD stores it on the server.
        
        """
        product = product.upper() # RQ or RE

        # Set up cache names for lookup
        cache_key = f"data_{product}_{timestamp}"
        cached_data = self.cache.get(cache_key)
        
        # If data already in cache -> success!
        if cached_data:
            return cached_data["values"], cached_data["flags"]

        # If not cached, actually get the data. File names are 
        target_filename = f"{product}{timestamp}.gz"
        file_url = f"{self.base_url}/{product.lower()}/{target_filename}"
        
        try:
            response = requests.get(file_url, timeout=15)
            response.raise_for_status()
            
            # Invoke RADOLAN/RADVOR parser
            metadata, values, flags = parse_radolan_composite(response.content)
            
            # Cache the parsed data
            self.cache.set(cache_key, {"values": values, "flags": flags}, expire=self.ttl)
            return values, flags
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Could not fetch or parse data for {target_filename}: {e}")

dwd_service = DWDService()
