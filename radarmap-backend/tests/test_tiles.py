import numpy as np
import pytest
from app.tiles import get_tile_bounds
from app.renderers import get_renderer
from PIL import Image


def test_get_tile_bounds():
    # Test zoom 0
    bounds = get_tile_bounds(0, 0, 0)
    expected = (-180.0, -85.05112859146761, 180.0, 85.05112859146761)
    assert bounds == pytest.approx(expected, abs=1e-6)


def test_render_tile_rq_numpy():
    data = np.zeros((900, 900), dtype=np.float32)
    # Put some data in the middle of Germany approx
    data[450, 450] = 5.0  # 5 mm/h

    # Center tile for zoom 6 (approx Germany)
    # z/x/y = 6/33/21
    bounds = get_tile_bounds(6, 33, 21)
    
    # Use explicit numpy renderer for CI compatibility
    engine = get_renderer("numpy")
    tile = engine.render(data, bounds, product="RQ", flags=None, size=256, interpolation="nearest")

    assert isinstance(tile, Image.Image)
    assert tile.size == (256, 256)
    assert tile.mode == "RGBA"

    # Check if there's any non-transparent pixel
    pixels = np.array(tile)
    assert np.any(pixels[:, :, 3] > 0)


def test_render_tile_re_hail_numpy():
    data = np.ones((900, 900), dtype=np.float32)  # All 1.0 (Solid)
    flags = np.ones((900, 900), dtype=np.uint16)  # Bit 0 set (Hail)

    bounds = get_tile_bounds(6, 33, 21)
    
    engine = get_renderer("numpy")
    tile = engine.render(data, bounds, product="RE", flags=flags, size=256, interpolation="nearest")

    pixels = np.array(tile)
    # Hail color is (255, 0, 255, 200)
    # Find any pixel that is hail color
    hail_color = [255, 0, 255, 200]
    is_hail = np.all(pixels == hail_color, axis=-1)
    assert np.any(is_hail)
