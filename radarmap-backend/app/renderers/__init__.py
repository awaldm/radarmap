from app.renderers.base import RenderingProvider

# Cache for instantiated renderers
_RENDERER_CACHE = {}


def get_renderer(name: str) -> RenderingProvider:
    """
    Factory to retrieve a specific rendering implementation.
    Lazy-loads the requested renderer to avoid initializing CUDA on CPU-only systems.
    """
    name = name.lower()

    if name in _RENDERER_CACHE:
        return _RENDERER_CACHE[name]

    if name == "numba":
        from app.renderers.cuda import CudaRenderer

        renderer = CudaRenderer()
    else:
        # Default to numpy
        from app.renderers.cpu import NumpyRenderer

        renderer = NumpyRenderer()

    _RENDERER_CACHE[name] = renderer
    return renderer
