"""
Module for extracting various pieces of information from EPUB files.
"""
import io
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import base64

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from PIL import Image

from src.core.models import CoverData, IsbnData, ExtractionResult, ExtractedMetadata, TextPreviewData

logger = logging.getLogger(__name__)

# ISBN Regex
ISBN_REGEX = re.compile(r"(?:ISBN(?:-1[03])?[:\s]?)?((?:97[89][-\s]?)?\d{1,5}[-\s]?\d{1,7}[-\s]?\d{1,6}[-\s]?\d{1,6}[-\s]?[\dX])")

def _normalize_isbn(value: str) -> str:
    """Normalize ISBN by removing separators and uppercasing."""
    return value.replace("-", "").replace(" ", "").replace(":", "").upper()

# --- Hashing ---

def get_file_hash(file_path: Path) -> str:
    """
    Calculates the SHA256 hash of a file.
    """
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

# --- Cover Extraction ---

def extract_cover(book: epub.EpubBook, file_path: Path) -> CoverData:
    """
    Checks for cover existence, extracts its metadata, and returns its binary content.
    """
    try:
        cover_item = None
        meta_cover = book.get_metadata('OPF', 'cover')
        if meta_cover:
            cover_id = meta_cover[0][1].get('content')
            cover_item = book.get_item_with_id(cover_id)

        if not cover_item:
            images = list(book.get_items_of_type(ebooklib.ITEM_IMAGE))
            if images:
                cover_item = images[0]

        if not cover_item:
            return CoverData(has_cover=False)

        image_bytes = cover_item.get_content()
        cover_filename = None
        cover_media_type = None

        get_name = getattr(cover_item, "get_name", None)
        if callable(get_name):
            cover_filename = get_name()
        else:
            cover_filename = getattr(cover_item, "file_name", None)

        get_media_type = getattr(cover_item, "get_media_type", None)
        if callable(get_media_type):
            cover_media_type = get_media_type()
        else:
            cover_media_type = getattr(cover_item, "media_type", None)

        if cover_media_type and "svg" in cover_media_type.lower():
            return CoverData(has_cover=False)

        if cover_filename and cover_filename.lower().endswith(".svg"):
            return CoverData(has_cover=False)
        
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                width, height = img.size
                image_format = img.format
        except Exception as img_err:
            logger.warning(f"Could not parse cover image for {file_path.name}: {img_err}")
            width, height, image_format = None, None, None

        return CoverData(
            has_cover=True,
            cover_filename=cover_filename,
            cover_media_type=cover_media_type,
            cover_content=image_bytes,
            width=width,
            height=height,
            format=image_format
        )
    except Exception as e:
        logger.error(f"Error extracting cover from {file_path.name}: {e}")
        return CoverData(has_cover=False, error=str(e))

def extract_cover_images(book: epub.EpubBook, file_path: Path) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Extracts every image from the EPUB, encodes it, and identifies the primary candidate.
    """
    doc_items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))[:3]
    image_lookup: Dict[str, int] = {}
    for order, doc in enumerate(doc_items):
        content = doc.get_content()
        soup = BeautifulSoup(content, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src")
            if not src:
                continue
            cleaned = src.split("#")[0].split("?")[0]
            normalized = Path(cleaned).name
            image_lookup[normalized] = min(order, image_lookup.get(normalized, order))

    ordered_images: List[Tuple[float, Dict[str, Any]]] = []
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        try:
            image_bytes = item.get_content()
        except Exception as e:
            logger.warning(f"Impossible de lire l'image {item} dans {file_path.name}: {e}")
            continue

        cover_filename = getattr(item, "file_name", None) or ""
        cover_media_type = getattr(item, "media_type", None)
        normalized_name = Path(cover_filename).name if cover_filename else ""
        if cover_media_type and "svg" in cover_media_type.lower():
            continue
        if normalized_name.lower().endswith(".svg"):
            continue

        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                width, height = img.size
                image_format = img.format
        except Exception as img_err:
            logger.warning(f"Impossible de parser l'image {file_path.name}: {img_err}")
            width = height = None
            image_format = None

        if width and height and (width < 300 or height < 300):
            continue

        order_index = image_lookup.get(normalized_name)
        payload = {
            "filename": cover_filename,
            "media_type": cover_media_type,
            "width": width,
            "height": height,
            "format": image_format,
            "bytes": image_bytes,
        }

        priority = float("inf") if order_index is None else float(order_index)
        ordered_images.append((priority, payload))

    ordered_images.sort(key=lambda pair: (pair[0], -(pair[1].get("width") or 0)))
    images_payload = [payload for _, payload in ordered_images]
    primary = images_payload[0] if images_payload else None
    if primary:
        primary["primary"] = True

    return images_payload, primary

# --- ISBN Extraction ---

def _is_valid_isbn(isbn: str) -> bool:
    """Validates an ISBN-10 or ISBN-13."""
    isbn = _normalize_isbn(isbn)
    if len(isbn) == 10:
        if not isbn[:-1].isdigit() or not (isbn[-1].isdigit() or isbn[-1] == 'X'):
            return False
        total = sum(int(digit) * (10 - i) for i, digit in enumerate(isbn[:-1]))
        last_digit = isbn[-1]
        check_digit = 11 - (total % 11)
        if check_digit == 11:
            check = '0'
        elif check_digit == 10:
            check = 'X'
        else:
            check = str(check_digit)
        return last_digit == check
    elif len(isbn) == 13:
        if not isbn.isdigit():
            return False
        total = sum(int(digit) * (1 if i % 2 == 0 else 3) for i, digit in enumerate(isbn[:-1]))
        check_digit = (10 - (total % 10)) % 10
        return str(check_digit) == isbn[-1]
    return False

def _find_isbns_in_text(text: str) -> List[str]:
    """Finds all valid ISBNs in a block of text."""
    found_isbns = []
    for match in ISBN_REGEX.finditer(text):
        potential_isbn = match.group(1).strip()
        normalized = _normalize_isbn(potential_isbn)
        if _is_valid_isbn(normalized):
            found_isbns.append(normalized)
    return list(dict.fromkeys(found_isbns))

def extract_isbn(book: epub.EpubBook, file_path: Path) -> IsbnData:
    """
    Extracts ISBN from an EPUB file, first from metadata, then from content.
    """
    try:
        identifiers = book.get_metadata("DC", "identifier")
        for identifier, _ in identifiers:
            if not identifier:
                continue
            if "isbn" in identifier.lower() or _is_valid_isbn(identifier):
                clean_isbn = _normalize_isbn(identifier.replace("urn:isbn:", "").strip())
                if _is_valid_isbn(clean_isbn):
                    logger.debug(f"ISBN found in metadata for {file_path.name}: {clean_isbn}")
                    return IsbnData(isbn=clean_isbn, isbn_source="metadata", all_isbns=[clean_isbn], isbn_candidates=[clean_isbn])

        all_found_isbns = []
        items_to_scan = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))[:5]
        for item in items_to_scan:
            content = item.get_content()
            soup = BeautifulSoup(content, 'html.parser')
            isbns = _find_isbns_in_text(soup.get_text())
            if isbns:
                all_found_isbns.extend(isbns)

        if all_found_isbns:
            unique_isbns = list(dict.fromkeys(all_found_isbns))
            isbn13 = next((isbn for isbn in unique_isbns if len(isbn) == 13), None)
            chosen_isbn = isbn13 or unique_isbns[0]
            logger.debug(f"ISBN found in content of {file_path.name}: {chosen_isbn}")
            return IsbnData(isbn=chosen_isbn, isbn_source="content", all_isbns=unique_isbns, isbn_candidates=unique_isbns)

        logger.debug(f"No ISBN found for {file_path.name}")
        return IsbnData()

    except Exception as e:
        logger.error(f"Error extracting ISBN from {file_path.name}: {e}")
        return IsbnData(error=str(e))

# --- Metadata Extraction ---

def extract_epub_metadata(book: epub.EpubBook, file_path: Path) -> ExtractionResult:
    """
    Extracts metadata from an EPUB file.
    """
    try:
        raw_metadata = {
            "title": book.get_metadata("DC", "title"),
            "creator": book.get_metadata("DC", "creator"),
            "publisher": book.get_metadata("DC", "publisher"),
            "date": book.get_metadata("DC", "date"),
            "identifier": book.get_metadata("DC", "identifier"),
            "language": book.get_metadata("DC", "language"),
            "description": book.get_metadata("DC", "description"),
            "subjects": book.get_metadata("DC", "subject"),
        }
        cleaned_metadata = {}
        for key, value in raw_metadata.items():
            if isinstance(value, list) and value:
                if len(value) == 1:
                    cleaned_metadata[key] = value[0][0] if isinstance(value[0], tuple) else value[0]
                else:
                    cleaned_metadata[key] = [v[0] if isinstance(v, tuple) else v for v in value]
        
        return ExtractionResult(metadata=ExtractedMetadata(**cleaned_metadata))
    except Exception as e:
        logger.error(f"Could not extract metadata from {file_path.name}: {e}")
        return ExtractionResult(error=str(e))

# --- Text Preview Extraction ---

def extract_text_preview(book: epub.EpubBook, file_path: Path, max_chars: int) -> TextPreviewData:
    """
    Extracts the first characters of text content from an EPUB.
    """
    text_content = []
    current_length = 0

    try:
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))

        for item in items:
            if current_length >= max_chars:
                break

            content = item.get_content()
            soup = BeautifulSoup(content, "html.parser")
            
            for tag in soup(["script", "style"]):
                tag.decompose()

            chunk = soup.get_text(" ", strip=True)
            
            if chunk:
                needed_chars = max_chars - current_length
                text_content.append(chunk[:needed_chars])
                current_length += len(chunk)

        full_text = "".join(text_content)
        preview = full_text[:max_chars]

        lang_meta = book.get_metadata("DC", "language")
        language = lang_meta[0][0] if lang_meta and lang_meta[0] else None

        return TextPreviewData(
            text_preview=preview,
            extracted_chars=len(preview),
            language=language
        )
    except Exception as e:
        logger.error(f"Could not extract text from {file_path.name}: {e}")
        return TextPreviewData(error=str(e))
