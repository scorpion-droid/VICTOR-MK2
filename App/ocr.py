from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import certifi
import cv2
import easyocr
import numpy as np
from PIL import Image, ImageOps, ImageFilter

os.environ["SSL_CERT_FILE"] = certifi.where()


@lru_cache(maxsize=1)
def get_ocr_reader() -> easyocr.Reader:
    return easyocr.Reader(["en"], gpu=False)


def preprocess_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    image = image.convert("L")
    image = ImageOps.autocontrast(image)
    image = image.resize((image.width * 0.5, image.height * 0.5), Image.Resampling.LANCZOS)

    array = np.array(image)
    array = cv2.fastNlMeansDenoising(array, None, h=8, templateWindowSize=7, searchWindowSize=21)

    return Image.fromarray(array)


def clean_ocr_text(text: str) -> str:
    text = text.replace("×", "*").replace("÷", "/").replace("−", "-")
    text = text.replace("{", "").replace("}", "").replace("|", "")
    return text.strip()

MATH_ALLOWLIST = "0123456789xX+-*/^=()."


def extract_text_from_image(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    image = Image.open(path)
    image = preprocess_image(image)

    reader = get_ocr_reader()
    detections = reader.readtext(
        np.array(image),
        detail=1,
        paragraph=False,
        allowlist=MATH_ALLOWLIST,
    )

    lines = []
    for _, text, confidence in detections:
        if confidence < 0.3:
            continue
        text = clean_ocr_text(text)
        if text:
            lines.append(text)

    return "\n".join(lines)

def extract_steps_from_image(image_path: str) -> list[str]:
    text = extract_text_from_image(image_path)
    return [line.strip() for line in text.splitlines() if line.strip()]