"""
Module for extracting various pieces of information from EPUB files.
"""
import io
import logging
import re
from pathlib import Path
from typing import Dict, Any, List
import hashlib

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from PIL import Image

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

def extract_cover(file_path: Path) -> Dict[str, Any]:
    """
    Checks for cover existence, extracts its metadata, and returns its binary content.
    """
    try:
        book = epub.read_epub(file_path, options={"ignore_ncx": True})
        
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
            return {"has_cover": False, "cover_content": None}

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
        
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                width, height = img.size
                image_format = img.format
        except Exception as img_err:
            logger.warning(f"Could not parse cover image for {file_path.name}: {img_err}")
            width, height, image_format = None, None, None

        return {
            "has_cover": True,
            "cover_filename": cover_filename,
            "cover_media_type": cover_media_type,
            "cover_content": image_bytes,
            "width": width,
            "height": height,
            "format": image_format
        }
    except Exception as e:
        logger.error(f"Error extracting cover from {file_path.name}: {e}")
        return {"has_cover": False, "cover_content": None, "error": str(e)}

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

def extract_isbn(file_path: Path) -> Dict[str, Any]:
    """
    Extracts ISBN from an EPUB file, first from metadata, then from content.
    """
    try:
        book = epub.read_epub(file_path)

        identifiers = book.get_metadata("DC", "identifier")
        for identifier, _ in identifiers:
            if "isbn" in identifier.lower() or _is_valid_isbn(identifier):
                clean_isbn = _normalize_isbn(identifier.replace("urn:isbn:", "").strip())
                if _is_valid_isbn(clean_isbn):
                    logger.debug(f"ISBN found in metadata for {file_path.name}: {clean_isbn}")
                    return {
                        "isbn": clean_isbn,
                        "isbn_source": "metadata",
                        "all_isbns": [clean_isbn],
                        "isbn_candidates": [clean_isbn],
                    }

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
            return {
                "isbn": chosen_isbn,
                "isbn_source": "content",
                "all_isbns": unique_isbns,
                "isbn_candidates": unique_isbns,
            }

        logger.debug(f"No ISBN found for {file_path.name}")
        return {"isbn": None, "isbn_source": "none", "all_isbns": [], "isbn_candidates": []}

    except Exception as e:
        logger.error(f"Error extracting ISBN from {file_path.name}: {e}")
        return {"isbn": None, "isbn_source": "error", "all_isbns": [], "isbn_candidates": [], "error": str(e)}

# --- Metadata Extraction ---

def extract_epub_metadata(file_path: Path) -> Dict[str, Any]:
    """
    Extracts metadata from an EPUB file.
    """
    try:
        book = epub.read_epub(file_path)
        metadata = {
            "title": book.get_metadata("DC", "title"),
            "creator": book.get_metadata("DC", "creator"),
            "publisher": book.get_metadata("DC", "publisher"),
            "date": book.get_metadata("DC", "date"),
            "identifier": book.get_metadata("DC", "identifier"),
            "language": book.get_metadata("DC", "language"),
            "description": book.get_metadata("DC", "description"),
            "subjects": book.get_metadata("DC", "subject"),
        }
        for key, value in metadata.items():
            if isinstance(value, list) and value:
                if len(value) == 1:
                    metadata[key] = value[0][0] if isinstance(value[0], tuple) else value[0]
                else:
                    metadata[key] = [v[0] if isinstance(v, tuple) else v for v in value]

        return {"metadata": metadata}
    except Exception as e:
        logger.error(f"Could not extract metadata from {file_path.name}: {e}")
        return {"error": str(e)}

# --- Text Preview Extraction ---

def extract_text_preview(file_path: Path, max_chars: int) -> Dict[str, Any]:
    """
    Extracts the first characters of text content from an EPUB.
    """
    text_content = []
    current_length = 0

    try:
        book = epub.read_epub(file_path)
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

        return {
            "text_preview": preview,
            "extracted_chars": len(preview),
            "language": book.get_metadata("DC", "language")[0][0] if book.get_metadata("DC", "language") else None
        }
    except Exception as e:
        logger.error(f"Could not extract text from {file_path.name}: {e}")
        return {"text_preview": None, "extracted_chars": 0, "error": str(e)}
