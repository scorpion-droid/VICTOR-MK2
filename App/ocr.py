from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import easyocr  
from PIL import Image, ImageOps, ImageFilter

@lru_cache(maxsize=1)

def get_ocr_reader() -> easyocr.Reader:
    return easyocr.Reader(["en"], gpu=False)

def preprocess_image (image: Image.Image) -> Image.Image:
   image = image.convert("L")
   image = ImageOps.autocontrast(image)
   image = image.filter(ImageFilter.SHARPEN)
   return image

def extract_text_from_image(image_path: Path) -> str:
    path = Path(image_path)
    if not path_exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    image = Image.open(image_path)
    image = preprocess_image(image)
    reader = get_ocr_reader()
    result = reader.readtext(np.array(image), detail=0, paragraph=False)
    return " ".join(line.strip() for line in result if line.strip())

def extract_steps_from_image(image_path: str) -> list[str]:

    text = extract_text_from_image(image_path)
    return [line.strip() for line in text.splitlines() if line.strip()]

