from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PADDLEX_CACHE_DIR = PROJECT_ROOT / ".paddlex"
MPL_CACHE_DIR = PROJECT_ROOT / ".matplotlib"

PADDLEX_CACHE_DIR.mkdir(exist_ok=True)
MPL_CACHE_DIR.mkdir(exist_ok=True)

os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(PADDLEX_CACHE_DIR))
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE_DIR))

from paddleocr import PaddleOCR


@lru_cache(maxsize=1)
def get_ocr_reader() -> PaddleOCR:
    return PaddleOCR(
        lang="en",
        ocr_version="PP-OCRv6",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_det_limit_side_len=1920,
        text_det_thresh=0.2,
        text_det_box_thresh=0.3,
        text_rec_score_thresh=0.0,
        return_word_box=False,
    )


def preprocess_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    image = ImageOps.autocontrast(image)

    if max(image.size) < 1200:
        image = image.resize(
            (int(image.width * 1.4), int(image.height * 1.4)),
            Image.Resampling.LANCZOS,
        )

    return image


def clean_ocr_text(text: str) -> str:
    text = text.replace("×", "*").replace("÷", "/").replace("−", "-")
    text = text.replace("{", "").replace("}", "").replace("|", "")
    text = text.replace(" ", "")
    return text.strip()


def _box_bounds(box) -> tuple[float, float, float, float]:
    points = np.asarray(box, dtype=float)
    if points.ndim == 1 and points.size == 4:
        x0, y0, x1, y1 = points.tolist()
        return float(x0), float(y0), float(x1), float(y1)

    points = points.reshape(-1, 2)
    xs = points[:, 0]
    ys = points[:, 1]
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def group_detections_into_lines(detections) -> list[str]:
    if not detections:
        return []

    items: list[tuple[float, float, float, str]] = []
    heights: list[float] = []

    for box, text in detections:
        x0, y0, x1, y1 = _box_bounds(box)
        x_center = (x0 + x1) / 2
        y_center = (y0 + y1) / 2
        width = x1 - x0
        height = y1 - y0
        items.append((y_center, x_center, width, str(text)))
        heights.append(height)

    tolerance = max(10.0, (sum(heights) / len(heights)) * 0.55)
    items.sort(key=lambda item: (item[0], item[1]))

    lines: list[list[tuple[float, float, str]]] = []
    current_line: list[tuple[float, float, str]] = []
    current_y: float | None = None

    for y_center, x_center, width, text in items:
        if current_y is None or abs(y_center - current_y) <= tolerance:
            current_line.append((x_center, width, text))
            current_y = y_center if current_y is None else (current_y + y_center) / 2
        else:
            lines.append(current_line)
            current_line = [(x_center, width, text)]
            current_y = y_center

    if current_line:
        lines.append(current_line)

    rendered: list[str] = []
    for line in lines:
        line.sort(key=lambda item: item[0])
        cleaned_tokens: list[str] = []
        for _, _, token in line:
            cleaned = clean_ocr_text(token)
            if cleaned:
                cleaned_tokens.append(cleaned)

        if not cleaned_tokens:
            continue

        text = "".join(cleaned_tokens)
        rendered.append(text)

    return rendered


def _predict_lines(image: Image.Image) -> list[str]:
    reader = get_ocr_reader()
    results = reader.predict(
        np.array(image),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_det_limit_side_len=1920,
        text_det_thresh=0.2,
        text_det_box_thresh=0.3,
        return_word_box=False,
    )

    if not results:
        return []

    result = results[0]
    boxes = result.get("rec_boxes", [])
    texts = result.get("rec_texts", [])
    detections = list(zip(boxes, texts))
    return group_detections_into_lines(detections)


def extract_text_from_image(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    raw_image = Image.open(path).convert("RGB")
    raw_lines = _predict_lines(raw_image)

    if len(raw_lines) >= 3 and any("=" in line for line in raw_lines):
        return "\n".join(raw_lines)

    processed_lines = _predict_lines(preprocess_image(raw_image))
    if len(processed_lines) > len(raw_lines):
        return "\n".join(processed_lines)

    return "\n".join(raw_lines)


def extract_steps_from_image(image_path: str) -> list[str]:
    text = extract_text_from_image(image_path)
    return [line.strip() for line in text.splitlines() if line.strip()]
