from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import certifi

os.environ["SSL_CERT_FILE"] = certifi.where()

import easyocr
import numpy as np
from PIL import Image, ImageFilter, ImageOps
import re


@lru_cache(maxsize=1)
def get_ocr_reader() -> easyocr.Reader:
    return easyocr.Reader(["en"], gpu=False)


def preprocess_image(image: Image.Image) -> Image.Image:
    image = image.convert("L")
    image = ImageOps.autocontrast(image)
    image = image.filter(ImageFilter.SHARPEN)
    return image


def extract_text_from_image(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    image = Image.open(path)
    image = preprocess_image(image)

    reader = get_ocr_reader()
    results = reader.readtext(np.array(image), detail=0, paragraph=False)

    return "\n".join(line.strip() for line in results if line.strip())


def extract_steps_from_image(image_path: str) -> list[str]:
    text = extract_text_from_image(image_path)
    return [line.strip() for line in text.splitlines() if line.strip()]

def clean_ocr_text(text: str) -> str:
    text = text.replace("×", "*").replace("÷", "/").replace("−", "-")
    text = text.replace("{", "").replace("}", "").replace("|", "")
    text = re.sub(r"[^\w\s+\-*/^=().]", "", text)
    return text