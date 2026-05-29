import numpy as np
from app.parser import parse_radolan_composite


def test_parse_header():
    from app.parser import parse_header

    header = (
        "RQ1212121212BY  162VS 3SW   1.5.0PR E-01INT  60GP 900x 900"
        "VV   0MF 0001QN 001MS 001ST 001RM 001"
    )
    metadata = parse_header(header)
    assert metadata["product"] == "RQ"
    assert metadata["GP"] == "900x 900"
    assert metadata["PR"] == "E-01"


def test_parse_radolan_composite_mock():
    # Create a mock binary RADOLAN content
    # Header + ETX + 900x900 uint16
    header = "RQ1105261200BY  162VS 3SW   1.5.0PR E-01INT  60GP 900x 900\x03"
    header_bytes = header.encode("latin-1")

    # 900x900 grid, all values = 10 (which is 1.0 mm/h with E-01)
    data_size = 900 * 900
    data = np.full(data_size, 10, dtype=np.uint16)
    binary_data = data.tobytes()

    content = header_bytes + binary_data

    metadata, values, flags = parse_radolan_composite(content)

    assert metadata["product"] == "RQ"
    assert values.shape == (900, 900)
    assert np.allclose(values, 1.0)
    assert np.all(flags == 0)
