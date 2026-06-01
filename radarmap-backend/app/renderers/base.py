from abc import ABC, abstractmethod
import numpy as np
from PIL import Image

class RenderingProvider(ABC):
    @abstractmethod
    def render(self, data: np.ndarray, tile_bounds: tuple, product: str, flags: np.ndarray, size: int, interpolation: str) -> Image.Image:
        """
        Base interface for all rendering paths (CPU, GPU, etc.)
        """
        pass
