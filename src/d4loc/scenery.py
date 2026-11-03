"""The window background: one photograph, shipped inside the application (background.jpg, CC0, see NOTICE).

It is read once and kept in memory; the window scales it to its size. If the file is missing, the window simply has a plain background.
"""
import os
from functools import lru_cache

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "background.jpg")


@lru_cache(maxsize=1)
def image():
    """PIL.Image (RGB) with the background, or None if the file cannot be read."""
    try:
        from PIL import Image
        return Image.open(FILE).convert("RGB")
    except OSError:
        return None
