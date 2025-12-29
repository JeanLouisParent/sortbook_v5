"""
Pipeline minimaliste : extraction locale puis un seul appel n8n.
"""
import base64
import datetime
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

import httpx
from asyncpg.pool import Pool
from ebooklib import epub

from src.config import Settings
from src.core.models import (
    CoverData,
    ExtractionResult,
    IsbnData,
    TextPreviewData,
    WorkflowResponse,
)
from src.db import database as db
from src.tasks import extract, integrate, ocr

logger = logging.getLogger(__name__)


class PipelineState:
    """Contient l'état et les données collectées pour un fichier."""

    def __init__(self, file_path: Path, settings: Settings):
        self.file_path = file_path
        self.settings = settings
        self.book_id: Optional[str] = None
        self.data: Dict[str, Any] = {}
        self.final_status: str = "pending"
        self.error_message: Optional[str] = None
        self.cover_images: List[Dict[str, Any]] = []
        self.primary_cover: Optional[Dict[str, Any]] = None
        self.n8n_response: Optional[WorkflowResponse] = None


def _is_svg(image: Dict[str, Any]) -> bool:
    filename = (image.get("filename") or "").lower()
    media_type = (image.get("media_type") or "").lower()
    if filename.endswith(".svg") or "svg" in media_type:
        return True
    bytes_data = image.get("bytes")
    if isinstance(bytes_data, (bytes, bytearray)):
        start = bytes_data.lstrip()
        if start.lower().startswith(b"<svg"):
            return True
    return False


def _build_cover_payload(state: PipelineState) -> Dict[str, Any]:
    cover_meta = state.data.get("json_extract_cover") or {}

    def _serialize(image: Dict[str, Any], include_base64: bool) -> Dict[str, Any]:
        entry = {
            "filename": image.get("filename"),
            "media_type": image.get("media_type"),
            "width": image.get("width"),
            "height": image.get("height"),
            "format": image.get("format"),
        }
        bytes_value = image.get("bytes")
        entry["content_base64"] = (
            base64.b64encode(bytes_value).decode("ascii") if bytes_value and include_base64 else None
        )
        return entry

    filtered_images = [img for img in state.cover_images if not _is_svg(img)]
    primary_candidate = state.primary_cover if state.primary_cover and not _is_svg(state.primary_cover) else None
    if not primary_candidate and filtered_images:
        primary_candidate = filtered_images[0]

    images = [_serialize(img, include_base64=False) for img in filtered_images]
    primary = _serialize(primary_candidate, include_base64=True) if primary_candidate else None

    return {
        "primary": primary,
        "images": images,
        **({"selected": cover_meta} if cover_meta else {}),
    }


def _build_n8n_payload(state: PipelineState, dry_run: bool, test_mode: bool) -> Dict[str, Any]:
    def _dedupe(values: List[str]) -> List[str]:
        return list(dict.fromkeys(value for value in values if value))

    def _collect_ocr_isbns() -> List[str]:
        ocr_results = state.data.get("image_ocr") or []
        found: List[str] = []
        for entry in ocr_results:
            text = entry.get("text")
            if not text:
                continue
            found.extend(extract._find_isbns_in_text(text))
        return _dedupe(found)

    def _build_isbn_payload() -> Dict[str, List[str]]:
        metadata_isbns: List[str] = []
        text_isbns: List[str] = []
        ocr_isbns = _collect_ocr_isbns()

        isbn_data = state.data.get("json_extract_isbn") or {}
        if isbn_data.get("isbn_source") == "metadata" and isbn_data.get("isbn"):
            metadata_isbns = [isbn_data.get("isbn")]
        elif isbn_data.get("isbn_source") == "content":
            text_isbns = isbn_data.get("all_isbns") or []

        sources: Dict[str, List[str]] = {"metadata": [], "text": [], "ocr": []}
        seen: set[str] = set()
        for source, values in (
            ("metadata", _dedupe(metadata_isbns)),
            ("text", _dedupe(text_isbns)),
            ("ocr", _dedupe(ocr_isbns)),
        ):
            for value in values:
                if value in seen:
                    continue
                sources[source].append(value)
                seen.add(value)
        return sources

    return {
        "filename": state.file_path.name,
        "metadata": (state.data.get("json_extract_metadata") or {}).get("metadata"),
        "isbn": _build_isbn_payload(),
        "ocr": state.data.get("image_ocr"),
        "text_preview": (state.data.get("json_extract_text") or {}).get("text_preview"),
    }


async def _extract_local_data(state: PipelineState):
    """Charge le livre et extrait les données locales."""
    try:
        book = epub.read_epub(state.file_path)
    except Exception as exc:
        logger.error("Impossible de lire le fichier EPUB %s: %s", state.file_path.name, exc)
        raise

    metadata_result: ExtractionResult = extract.extract_epub_metadata(book, state.file_path)
    metadata_dump = metadata_result.model_dump()
    state.data["json_extract_metadata"] = metadata_dump
    state.data["epub_metadata"] = metadata_dump

    isbn_data: IsbnData = extract.extract_isbn(book, state.file_path)
    state.data["json_extract_isbn"] = isbn_data.model_dump()
    if isbn_data.isbn:
        state.data["isbn"] = isbn_data.isbn
        state.data["isbn_source"] = isbn_data.isbn_source
        state.data["isbn_candidates"] = isbn_data.isbn_candidates

    text_preview: TextPreviewData = extract.extract_text_preview(
        book, state.file_path, state.settings.text_preview_chars
    )
    state.data["json_extract_text"] = text_preview.model_dump()
    state.data["text_preview"] = text_preview.text_preview

    cover_data: CoverData = extract.extract_cover(book, state.file_path)
    state.cover_images, state.primary_cover = extract.extract_cover_images(book, state.file_path)
    state.data["image_ocr"] = ocr.extract_text_from_images(
        state.cover_images,
        languages=state.settings.ocr_languages,
        max_chars=state.settings.ocr_max_chars,
        use_gpu=state.settings.ocr_use_gpu,
        detail=state.settings.ocr_detail,
        paragraph=state.settings.ocr_paragraph,
        contrast_ths=state.settings.ocr_contrast_ths,
        adjust_contrast=state.settings.ocr_adjust_contrast,
        text_threshold=state.settings.ocr_text_threshold,
        low_text=state.settings.ocr_low_text,
        link_threshold=state.settings.ocr_link_threshold,
    )
    state.data["has_cover"] = cover_data.has_cover
    state.data["json_extract_cover"] = cover_data.model_dump(exclude={"cover_content"})


async def _call_n8n_workflow(
    state: PipelineState,
    dry_run: bool,
    test_mode: bool,
    http_client: httpx.AsyncClient,
) -> Tuple[WorkflowResponse, Any]:
    payload = _build_n8n_payload(state, dry_run, test_mode)
    normalized, raw_result = await integrate.call_n8n_sortebook_workflow(
        payload, state.settings, test_mode, http_client
    )
    parsed = WorkflowResponse.model_validate(normalized)
    return parsed, raw_result


async def run_pipeline(
    file_path: Path,
    pool: Pool,
    settings: Settings,
    dry_run: bool,
    test_mode: bool,
    use_n8n_test: bool,
    http_client: httpx.AsyncClient,
):
    """Exécute le pipeline pour un fichier EPUB."""
    start_time = datetime.datetime.now(datetime.timezone.utc)
    state = PipelineState(file_path, settings)

    try:
        state.data["file_hash"] = extract.get_file_hash(file_path)

        existing_book = await db.find_book_by_hash(pool, state.data["file_hash"])
        if existing_book:
            state.final_status = "duplicate_hash"
            state.data["status"] = state.final_status
            return state.data

        state.book_id = await db.create_book_entry(
            pool,
            state.data["file_hash"],
            file_path.name,
            str(file_path),
            file_path.stat().st_size,
        )

        await _extract_local_data(state)

        if state.data.get("isbn"):
            existing_isbn = await db.find_book_by_isbn(pool, state.data["isbn"])
            if existing_isbn:
                state.final_status = "duplicate_isbn"
                state.error_message = "ISBN déjà traité"

        if state.final_status == "pending":
            should_use_test = test_mode or use_n8n_test
            state.n8n_response, raw_response = await _call_n8n_workflow(
                state, dry_run, should_use_test, http_client
            )
            state.data["json_n8n_response"] = raw_response
            state.data["json_n8n_response_parsed"] = state.n8n_response.model_dump()

            if state.n8n_response.success and state.n8n_response.payload:
                state.data["final_title"] = state.n8n_response.payload.title
                state.data["final_author"] = state.n8n_response.payload.author
                state.data["choice_source"] = state.n8n_response.source or "sortebook_v5"
                state.final_status = "processed"
            else:
                errors = " ; ".join(state.n8n_response.errors or [])
                state.error_message = errors or "SortBook workflow n8n a retourné une erreur"
                state.final_status = "failed"
        else:
            state.data["json_n8n_response"] = None
            state.data["json_n8n_response_parsed"] = None

    except Exception as exc:
        logger.exception("Erreur critique dans le pipeline pour %s", file_path.name)
        state.final_status = "failed"
        state.error_message = str(exc)

    finally:
        end_time = datetime.datetime.now(datetime.timezone.utc)
        state.data["status"] = state.final_status
        state.data["error_message"] = state.error_message
        state.data["processing_completed_at"] = end_time
        state.data["processing_time_ms"] = int((end_time - start_time).total_seconds() * 1000)

        if state.book_id:
            await db.update_book_entry(pool, state.book_id, state.data)

    return state.data
