"""
OCR helper that extracts text from image bytes using EasyOCR.
"""
import io
import logging
from typing import List, Dict, Any, Optional, Tuple

try:
    import easyocr
    import numpy as np
except ImportError:  # fallback when dependencies not installed yet
    easyocr = None  # type: ignore
    np = None  # type: ignore

from PIL import Image, ImageOps, ImageEnhance

logger = logging.getLogger(__name__)
_reader_cache: Dict[Tuple[Tuple[str, ...], bool], "easyocr.Reader"] = {}
OCR_AVAILABLE = easyocr is not None and np is not None
_ocr_warning_logged = False


def _get_reader(languages: Optional[List[str]] = None, use_gpu: bool = False):
    global _reader
    if not OCR_AVAILABLE:
        raise RuntimeError("EasyOCR / numpy is not available")

    langs = tuple(languages or ["fr", "en"])
    key = (langs, bool(use_gpu))
    reader = _reader_cache.get(key)
    if reader is None:
        reader = easyocr.Reader(list(langs), gpu=bool(use_gpu))
        _reader_cache[key] = reader
    return reader


def extract_text_from_images(
    images: List[Dict[str, Any]],
    languages: Optional[List[str]] = None,
    max_chars: int = 2000,
    use_gpu: bool = False,
    detail: int = 0,
    paragraph: bool = True,
    contrast_ths: float = 0.1,
    adjust_contrast: float = 0.5,
    text_threshold: float = 0.5,
    low_text: float = 0.4,
    link_threshold: float = 0.4,
) -> List[Dict[str, Any]]:
    def _resize_if_needed(image: Image.Image, min_dim: int = 1000) -> Image.Image:
        width, height = image.size
        current_min = min(width, height)
        if current_min >= min_dim:
            return image
        scale = min(2.5, float(min_dim) / float(current_min))
        new_size = (int(width * scale), int(height * scale))
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        return image.resize(new_size, resampling)

    def _preprocess_variants(image: Image.Image) -> List[Image.Image]:
        variants: List[Image.Image] = [image]
        gray = ImageOps.grayscale(image)
        variants.append(gray)
        auto = ImageOps.autocontrast(gray)
        variants.append(auto)
        enhanced = ImageEnhance.Contrast(auto).enhance(1.8)
        enhanced = ImageEnhance.Sharpness(enhanced).enhance(1.5)
        variants.append(enhanced)
        variants.append(_resize_if_needed(enhanced))
        return variants

    def _pick_best_text(texts: List[str]) -> str:
        if not texts:
            return ""
        return max(texts, key=lambda value: len(value))

    global _ocr_warning_logged
    if not OCR_AVAILABLE:
        if not _ocr_warning_logged:
            logger.warning("EasyOCR or numpy is not installed; image OCR disabled.")
            _ocr_warning_logged = True
        return []

    reader = _get_reader(languages, use_gpu)
    results: List[Dict[str, Any]] = []
    for image in images:
        image_bytes = image.get("bytes")
        if not image_bytes:
            continue
        filename = image.get("filename") or ""
        media_type = image.get("media_type") or ""
        if filename.lower().endswith(".svg") or "svg" in media_type.lower():
            continue

        try:
            pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            logger.warning("Impossible d'ouvrir l'image OCR %s : %s", image.get("filename"), exc)
            continue

        variants = _preprocess_variants(pil_image)
        collected_texts: List[str] = []
        try:
            for variant in variants:
                array = np.asarray(variant)
                text_blocks = reader.readtext(
                    array,
                    detail=detail,
                    paragraph=paragraph,
                    contrast_ths=contrast_ths,
                    adjust_contrast=adjust_contrast,
                    text_threshold=text_threshold,
                    low_text=low_text,
                    link_threshold=link_threshold,
                )
                joined = " ".join(text_blocks).strip()
                if joined:
                    collected_texts.append(joined)
        except Exception as exc:
            logger.warning("EasyOCR a échoué sur %s : %s", image.get("filename"), exc)
            continue

        joined = _pick_best_text(collected_texts)
        if not joined:
            continue

        if len(joined) > max_chars:
            joined = joined[:max_chars]

        results.append(
            {
                "filename": image.get("filename"),
                "text": joined,
            }
        )

    return results
