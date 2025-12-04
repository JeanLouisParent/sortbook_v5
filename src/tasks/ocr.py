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

from PIL import Image

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

        try:
            array = np.asarray(pil_image)
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
        except Exception as exc:
            logger.warning("EasyOCR a échoué sur %s : %s", image.get("filename"), exc)
            continue

        joined = " ".join(text_blocks).strip()
        if not joined:
            continue

        if len(joined) > max_chars:
            joined = joined[:max_chars]

        results.append(
            {
                "filename": image.get("filename"),
                "text": joined,
                "confidence": float(len(joined)) / max_chars,
            }
        )

    return results
