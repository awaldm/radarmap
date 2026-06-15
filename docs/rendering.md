# Rendering Pipeline

The following describes how Radarmap turns a DWD radar array into an XYZ map tile.
The same conceptual pipeline is used by both the CPU and CUDA renderers.

## Inputs

A tile render receives:

| Input | Description |
| :--- | :--- |
| `data` | Parsed radar values as a NumPy array. |
| `flags` | Optional product-specific quality or classification flags. |
| `tile_bounds` | Geographic bounds of the requested XYZ tile. |
| `product` | DWD product identifier such as `RQ`, `RE`, or `RS`. |
| `size` | Output tile width and height in pixels. |
| `interpolation` | Sampling mode, currently `nearest` or `bilinear`. |

The output is an RGBA image that the API serializes as a PNG tile.

## Pipeline Stages

### 1. Output Grid

The renderer creates a regular grid of output pixels for the requested tile
size. Each pixel position is mapped to longitude and latitude inside the tile
bounds.

For a `1024px` tile, this produces 1,048,576 coordinate pairs.

### 2. Projection

Each WGS84 coordinate is projected into the RADOLAN grid coordinate system.

In the CPU renderer this is handled by PyProj. In the CUDA renderer the relevant
projection math is implemented in Numba kernels. This is the main reason the two
renderers have different scaling behavior at larger tile sizes.

### 3. Radar Grid Indexing

Projected coordinates are converted into row and column positions in the source
radar array. Pixels outside the radar coverage area are masked out.

The conversion uses the RADOLAN grid origin and resolution:

```text
column = (x_radolan - x_origin) / 1000
row    = (y_radolan - y_origin) / 1000
```

The renderer uses a stricter valid range for bilinear interpolation because it
needs neighboring cells.

### 4. Sampling

The renderer samples the radar array at the computed grid positions.

`nearest` uses the containing grid cell. `bilinear` blends the four surrounding
cells for continuous-valued products. The current implementation avoids
bilinear interpolation for `RE` because that product represents categorical or
flag-like information rather than a continuous precipitation intensity field.

### 5. Colormapping

Sampled values are converted to RGBA pixels. Quantitative precipitation products
use a lookup table. `RE` has separate handling because its values and flags are
interpreted differently from precipitation intensity grids.

### 6. Serialization

The API serializes the returned image as PNG and streams it to the client.
Serialization is outside the renderer implementation, but it is part of
end-to-end tile latency.

## CPU Renderer

The CPU renderer is implemented in `app/renderers/cpu.py`.

It uses:

- NumPy for grid creation, indexing, masking, sampling, and color assignment
- PyProj for coordinate transformation
- Pillow image creation for the final RGBA array

This renderer is the compatibility baseline. It is useful for development,
testing, and environments without CUDA.

## CUDA Renderer

The CUDA renderer is implemented in `app/renderers/cuda.py`.

It uses:

- Numba CUDA kernels for projection and sampling
- device memory for the input array, flags, colormap, and output image
- a host copy at the end to create the Pillow image returned to the API

The CUDA renderer reduces the cost of per-pixel projection and sampling for
large tiles. It also introduces first-use overhead from kernel compilation and
device initialization, which is covered in the [performance report](performance.md).

## Performance Considerations

The expensive part of the CPU path is the per-pixel projection step. The CUDA
path moves this dense per-pixel work onto the GPU, which improves scaling for
larger tiles.

Once projection and sampling are faster, PNG serialization becomes a larger
share of total request time. For that reason, further performance work should
measure the full request path rather than only the renderer function.

Relevant measurements are maintained in the [performance report](performance.md).
