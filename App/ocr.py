from __future__ import annotations

import os
import unicodedata
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
    return _preprocess_image(image, aggressive=False)


def _preprocess_image(image: Image.Image, aggressive: bool) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    image = ImageOps.autocontrast(image)

    max_side = max(image.size)
    if max_side >= 1800:
        return image

    scale = 1.3 if not aggressive else 1.5
    if max_side < 1200 or aggressive:
        image = image.resize(
            (int(image.width * scale), int(image.height * scale)),
            Image.Resampling.LANCZOS,
        )

    return image


MATH_REPLACEMENTS = str.maketrans(
    {
        "×": "*",
        "÷": "/",
        "−": "-",
        "—": "-",
        "–": "-",
        "十": "+",
        "一": "=",
        "_": "1",
        "l": "1",
        "I": "1",
        "|": "1",
        "O": "0",
        "o": "0",
    }
)


def clean_ocr_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(MATH_REPLACEMENTS)
    text = text.replace("{", "").replace("}", "")
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

    items: list[tuple[float, float, float, str, float]] = []
    heights: list[float] = []

    for item in detections:
        if len(item) == 3:
            box, text, score = item
        else:
            box, text = item
            score = 1.0 
            
        x0, y0, x1, y1 = _box_bounds(box)
        x_center = (x0 + x1) / 2
        y_center = (y0 + y1) / 2
        width = x1 - x0
        height = y1 - y0
        items.append((y_center, x_center, width, str(text), float(score)))
        heights.append(height)

    tolerance = max(10.0, (sum(heights) / len(heights)) * 0.55)
    items.sort(key=lambda item: (item[0], item[1]))

    lines: list[list[tuple[float, float, str, float]]] = []
    current_line: list[tuple[float, float, str, float]] = []
    current_y: float | None = None

    # FIXED: Added score here to match the 5 values appended to items!
    for y_center, x_center, width, text, score in items:
        if current_y is None or abs(y_center - current_y) <= tolerance:
            current_line.append((x_center, width, text, score))
            current_y = y_center if current_y is None else (current_y + y_center) / 2
        else:
            lines.append(current_line)
            current_line = [(x_center, width, text, score)]
            current_y = y_center

    if current_line:
        lines.append(current_line)

    rendered: list[str] = []
    for line in lines:
        line.sort(key=lambda item: item[0])
        cleaned_tokens: list[str] = []
        
        is_line_blurry = False

        for _, _, token, score in line: 
            if score < 0.60: 
                is_line_blurry = True

            cleaned = clean_ocr_text(token)
            if cleaned: 
                cleaned_tokens.append(cleaned)

        if not cleaned_tokens:
            continue

        text = "".join(cleaned_tokens)
        
        if is_line_blurry:
            text = text + " ?" 
            
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
    scores = result.get("rec_scores", [])

    if not scores: 
        scores = [1.0] * len(texts)

    # FIXED: Added scores to the zip block so group_detections_into_lines receives it!
    detections = list(zip(boxes, texts, scores))
    return group_detections_into_lines(detections)


def extract_text_from_image(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    raw_image = Image.open(path).convert("RGB")
    raw_lines = _predict_lines(raw_image)
    raw_text = "\n".join(raw_lines)

    if len(raw_lines) >= 3 and any("=" in line for line in raw_lines):
        return raw_text

    processed_lines = _predict_lines(preprocess_image(raw_image))
    processed_text = "\n".join(processed_lines)

    if len(processed_lines) > len(raw_lines):
        return processed_text

    if len(raw_lines) <= 1:
        aggressive_lines = _predict_lines(_preprocess_image(raw_image, aggressive=True))
        aggressive_text = "\n".join(aggressive_lines)
        if len(aggressive_lines) > len(raw_lines) or len(aggressive_text) > len(raw_text):
            return aggressive_text

    if len(processed_lines) == len(raw_lines) and len(processed_text) > len(raw_text):
        return processed_text

    return raw_text


def extract_steps_from_image(image_path: str) -> list[str]:
    text = extract_text_from_image(image_path)
    return [line.strip() for line in text.splitlines() if line.strip()]