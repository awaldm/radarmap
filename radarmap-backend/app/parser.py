"""
File parser for RADOLAN/RADVOR files.
Handles both legacy binary composites and the new HDF5 (RS/RV) formats.
"""

import contextlib
import gzip
import io
import re

import numpy as np

try:
    import h5py
except ImportError:
    h5py = None


def parse_radolan_composite(file_content):
    """
    Parses a RADOLAN/RADVOR composite file (Binary or HDF5).

    This function automatically detects the format:
    1. Legacy Binary: Starts with product ID (e.g., RE, RQ) and ends with ETX (0x03).
    2. Modern HDF5: Used by the new RS/RV products.

    Args:
        file_content (bytes): The raw bytes of the radar file (can be gzipped).

    Returns:
        tuple:
            - metadata (dict): Dictionary of ASCII header keys or HDF5 attributes.
            - values (np.ndarray): 2D float32 array of precipitation values (mm/h).
            - flags (np.ndarray | None): 2D uint8 array of quality/hail flags (if available).
    """
    try:
        data = gzip.decompress(file_content)
    except (gzip.BadGzipFile, OSError):
        data = file_content

    header_end_marker = b"\x03"
    header_end_index = data.find(header_end_marker)
    if header_end_index == -1:
        # Fallback to HDF5 check if binary header not found
        if h5py and (data.startswith(b"\x89HDF\r\n\x1a\n") or data.startswith(b"HDF")):
            return parse_hdf5_composite(data)
        raise ValueError("Header end marker (ETX) not found in data.")

    header_str = data[:header_end_index].decode("latin-1")
    binary_data = data[header_end_index + 1 :]
    metadata = parse_header(header_str)

    if len(binary_data) % 2 != 0:
        binary_data = binary_data[:-1]

    dt = np.dtype(np.uint16).newbyteorder("<")
    radolan_data = np.frombuffer(binary_data, dtype=dt)

    # Determine shape (standard composite sizes)
    shape = (900, 900)
    if "GP" in metadata:
        match = re.search(r"(\d+)\s*x\s*(\d+)", metadata["GP"])
        if match:
            shape = (int(match.group(1)), int(match.group(2)))

    if radolan_data.size != shape[0] * shape[1]:
        # Last ditch heuristic for known DWD grid sizes
        if radolan_data.size == 1100 * 900:
            shape = (1100, 900)
        elif radolan_data.size == 1500 * 1400:
            shape = (1500, 1400)
        elif radolan_data.size == 1200 * 1100:
            shape = (1200, 1100)

    radolan_data = radolan_data.reshape(shape)

    # Values are 12-bit, Flags are top 4 bits in binary format
    values = (radolan_data & 0xFFF).astype(np.float32)
    flags = (radolan_data >> 12) & 0xF

    # Apply precision from PR value (e.g., E-01 = 0.1)
    precision = 0.1
    if "PR" in metadata:
        with contextlib.suppress(Exception):
            precision = 10 ** (-int(metadata["PR"].split("-")[1]))

    return metadata, values * precision, flags


def parse_hdf5_composite(file_content):
    """
    Parses a DWD HDF5 composite (the new RS/RV format).

    Expected structure: /dataset1/data1/data
    """
    if not h5py:
        raise ImportError("h5py is required to parse RS/RV HDF5 files.")

    # Wrap in BytesIO for h5py
    f = h5py.File(io.BytesIO(file_content), "r")

    try:
        ds = f["dataset1"]["data1"]
        data = ds["data"][:]
        metadata_attrs = dict(ds["what"].attrs)

        # Apply gain and offset
        gain = metadata_attrs.get("gain", 0.1)
        offset = metadata_attrs.get("offset", 0.0)
        nodata = metadata_attrs.get("nodata", 4294967295)

        # Mask nodata
        mask = data == nodata
        values = data.astype(np.float32) * gain + offset
        values[mask] = -1.0  # Standard internal nodata

        metadata = {
            "product": "RS",
            "datetime": "unknown",
            "shape": data.shape,
        }

        return metadata, values, None
    finally:
        f.close()


def parse_header(header_str):
    """
    Parses the ASCII header of a RADOLAN file.
    """
    metadata = {"product": header_str[:2]}
    match = re.search(r"(\d{6}\d{4})", header_str)
    if match:
        metadata["datetime"] = match.group(1)

    known_keys = ["BY", "VS", "SW", "PR", "INT", "GP", "VV", "MF", "QN", "MS", "ST", "RM"]
    for i, key in enumerate(known_keys):
        start_index = header_str.find(key)
        if start_index != -1:
            next_key_start = len(header_str)
            for next_key in known_keys[i + 1 :]:
                found_pos = header_str.find(next_key, start_index + len(key))
                if found_pos != -1:
                    next_key_start = found_pos
                    break
            metadata[key] = header_str[start_index + len(key) : next_key_start].strip()
    return metadata
