from app.renderers.base import RenderingProvider
from app.renderers.cpu import NumpyRenderer
from app.renderers.cuda import CudaRenderer

# Registry of available rendering implementations
RENDERERS = {
    "numpy": NumpyRenderer(),
    "numba": CudaRenderer(),
}


def get_renderer(name: str) -> RenderingProvider:
    """
    Factory to retrieve a specific rendering implementation.
    Defaults to 'numpy' if the requested name is unavailable.
    """
    return RENDERERS.get(name.lower(), RENDERERS["numpy"])
