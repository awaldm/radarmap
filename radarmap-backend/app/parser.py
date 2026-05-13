"""
File parser for RADVOR files.

All of this is derived from the descriptions in DWD's RADOLAN-RADVOR-Kompositformat_2.6.docx

"""
import gzip
import re
import numpy as np

def parse_radolan_composite(file_content):
    """
    Parses a RADOLAN composite file.

    Args:
        file_content: The content of the RADOLAN file (gzipped or not).

    Returns:
        A tuple containing:
        - metadata (dict): A dictionary of metadata from the header.
        - data (np.ndarray): A 2D NumPy array of the RADOLAN data.
    """
    try:
        data = gzip.decompress(file_content)
    except (gzip.BadGzipFile, OSError):
        # If the file is not gzipped, use the raw content
        data = file_content

    # The header ends with the ETX character (0x03)
    header_end_marker = b'\x03'
    header_end_index = data.find(header_end_marker)
    if header_end_index == -1:
        raise ValueError("Header end marker (ETX) not found in data.")

    header_str = data[:header_end_index].decode("latin-1")
    binary_data = data[header_end_index + 1:] # Start after the marker

    metadata = parse_header(header_str)

    if len(binary_data) % 2 != 0:
        binary_data = binary_data[:-1]

    dt = np.dtype(np.uint16).newbyteorder('<')
    radolan_data = np.frombuffer(binary_data, dtype=dt)

    if 'GP' in metadata:
        grid_size_str = metadata['GP'].strip()
        match = re.search(r"(\d+)\s*x\s*(\d+)", grid_size_str)
        if match:
            rows, cols = map(int, match.groups())
            expected_size = rows * cols
            if radolan_data.size == expected_size:
                 radolan_data = radolan_data.reshape((rows, cols))
            else:
                raise ValueError(f"Data size mismatch: expected {expected_size}, got {radolan_data.size}")
        else:
            raise ValueError(f"Could not parse grid size from GP value: {metadata['GP']}")
    elif radolan_data.size == 900 * 900:
        radolan_data = radolan_data.reshape((900, 900))
    elif radolan_data.size == 1100 * 900:
        radolan_data = radolan_data.reshape((1100, 900))
    elif radolan_data.size == 1500 * 1400:
        radolan_data = radolan_data.reshape((1500, 1400))
    else:
        raise ValueError(f"Could not determine grid size from data size {radolan_data.size}")


    # Process the data: extract flags and values
    # The last 4 bits are flags, the first 12 are the value
    values = radolan_data & 0xFFF
    flags = (radolan_data >> 12) & 0xF

    # Apply precision from PR value if available
    if 'PR' in metadata:
        pr_value_str = metadata.get('PR', 'E-01')
        try:
            # e.g., "E-01" -> 0.1
            precision = 10**(-int(pr_value_str.split('-')[1]))
            values = values.astype(np.float32) * precision
        except (ValueError, IndexError):
            # Fallback if PR value is malformed
            values = values.astype(np.float32) * 0.1
    else:
        values = values.astype(np.float32) * 0.1


    return metadata, values, flags

def parse_header(header_str):
    """
    Parses the ASCII header of a RADOLAN file.
    """
    metadata = {}
    
    # Product name is the first two characters
    metadata['product'] = header_str[:2]
    
    # Extract timestamp (ddhhmmMMYY)
    match = re.search(r'(\d{6}\d{4})', header_str)
    if match:
        metadata['datetime'] = match.group(1)

    # Extract key-value pairs
    # These are less consistently formatted. We'll find the keys and extract the value that follows.
    known_keys = ["BY", "VS", "SW", "PR", "INT", "GP", "VV", "MF", "QN", "MS", "ST", "RM"]
    
    for i, key in enumerate(known_keys):
        start_index = header_str.find(key)
        if start_index != -1:
            # Find the start of the next known key to delimit the current value
            next_key_start = len(header_str) # Default to end of string
            for next_key in known_keys[i+1:]:
                found_pos = header_str.find(next_key, start_index + len(key))
                if found_pos != -1:
                    next_key_start = found_pos
                    break
            
            value_str = header_str[start_index + len(key):next_key_start].strip()
            metadata[key] = value_str

    return metadata

