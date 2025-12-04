"""
Orchestration du pipeline de traitement pour un seul fichier EPUB.
"""
import datetime
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import httpx
from asyncpg.pool import Pool
from ebooklib import epub

from src.config import Settings
from src.core.models import WorkflowResponse
from src.db import database as db
from src.tasks import extract, integrate

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
        self.book: Optional[epub.EpubBook] = None
        self.n8n_isbn_response: Optional[WorkflowResponse] = None
        self.n8n_metadata_response: Optional[WorkflowResponse] = None

def _choose_final_data(state: PipelineState) -> Tuple[str, str, str]:
    """Logique de décision pour choisir le titre/auteur final à partir des workflows externes."""
    if state.n8n_isbn_response and state.n8n_isbn_response.success and state.n8n_isbn_response.payload:
        logger.debug(f"Choix final pour {state.file_path.name}: N8N ISBN")
        return state.n8n_isbn_response.payload.title, state.n8n_isbn_response.payload.author, "n8n_isbn"

    if state.n8n_metadata_response and state.n8n_metadata_response.success and state.n8n_metadata_response.payload:
        logger.debug(f"Choix final pour {state.file_path.name}: N8N metadata workflow")
        return state.n8n_metadata_response.payload.title, state.n8n_metadata_response.payload.author, "n8n_metadata"

    logger.warning(f"Impossible de déterminer un titre/auteur pour {state.file_path.name}")
    return "Unknown", "Unknown", "unknown"

async def _extract_local_data(state: PipelineState):
    """Charge le livre et en extrait toutes les données locales."""
    try:
        state.book = epub.read_epub(state.file_path)
    except Exception as e:
        logger.error(f"Impossible de lire le fichier EPUB {state.file_path.name}: {e}")
        raise IOError(f"Invalid EPUB file: {e}")

    metadata_result = extract.extract_epub_metadata(state.book, state.file_path)
    state.data["json_extract_metadata"] = metadata_result.model_dump()
    state.data["epub_metadata"] = metadata_result.metadata.model_dump() if metadata_result.metadata else None

    isbn_data = extract.extract_isbn(state.book, state.file_path)
    state.data["json_extract_isbn"] = isbn_data.model_dump()
    if isbn_data.isbn:
        state.data["isbn"] = isbn_data.isbn
        state.data["isbn_source"] = isbn_data.isbn_source
        state.data["isbn_candidates"] = isbn_data.all_isbns

    text_data = extract.extract_text_preview(state.book, state.file_path, state.settings.text_preview_chars)
    state.data["json_extract_text"] = text_data.model_dump()
    state.data["text_preview"] = text_data.text_preview
    
    cover_data = extract.extract_cover(state.book, state.file_path)
    state.data["has_cover"] = cover_data.has_cover
    state.data["json_extract_cover"] = cover_data.model_dump(exclude={'cover_content'})
    if cover_data.cover_content:
        state.data["cover_content_bytes"] = cover_data.cover_content

async def _enrich_data_from_apis(state: PipelineState, use_n8n_test: bool, http_client: httpx.AsyncClient):
    """Appelle les API externes pour enrichir les données."""
    if state.final_status in ["duplicate_hash", "duplicate_isbn"]:
        return

    metadata_payload = state.data.get("epub_metadata")
    isbn_candidates = state.data.get("isbn_candidates", [])
    
    should_call_metadata_workflow = True
    if state.data.get("isbn"):
        isbn_response_dict = await integrate.call_n8n_isbn_workflow(
            state.data["isbn"], state.settings, use_n8n_test, http_client,
            metadata=metadata_payload, source_filename=state.file_path.name, isbn_candidates=isbn_candidates
        )
        state.n8n_isbn_response = WorkflowResponse.model_validate(isbn_response_dict)
        state.data["json_n8n_isbn"] = state.n8n_isbn_response.model_dump()
        if state.n8n_isbn_response.success:
            should_call_metadata_workflow = False

    if metadata_payload and should_call_metadata_workflow:
        metadata_response_dict = await integrate.call_n8n_metadata_workflow(
            metadata_payload, state.settings, use_n8n_test, http_client, state.file_path.name
        )
        state.n8n_metadata_response = WorkflowResponse.model_validate(metadata_response_dict)
        state.data["json_n8n_metadata"] = state.n8n_metadata_response.model_dump()

def _finalize_processing(state: PipelineState):
    """Détermine les données finales, le statut et nettoie l'état."""
    if state.final_status == "pending":
        final_title, final_author, choice_source = _choose_final_data(state)
        state.data["final_title"] = final_title
        state.data["final_author"] = final_author
        state.data["choice_source"] = choice_source
        
        if choice_source != "unknown":
            state.final_status = "processed"
        else:
            state.final_status = "failed"
            state.error_message = "Impossible de déterminer le titre/auteur via les workflows."
    
    if "cover_content_bytes" in state.data:
        del state.data["cover_content_bytes"]

async def run_pipeline(
    file_path: Path, pool: Pool, settings: Settings, dry_run: bool,
    test_mode: bool, use_n8n_test: bool, http_client: httpx.AsyncClient,
) -> "PipelineState":
    """Exécute le pipeline complet pour un fichier EPUB."""
    start_time = datetime.datetime.now(datetime.timezone.utc)
    state = PipelineState(file_path, settings)
    
    try:
        state.data["file_hash"] = extract.get_file_hash(file_path)
        
        existing_book = await db.find_book_by_hash(pool, state.data["file_hash"])
        if existing_book:
            state.final_status = "duplicate_hash"
            state.data["status"] = state.final_status
            return state

        state.book_id = await db.create_book_entry(
            pool, state.data["file_hash"], file_path.name, str(file_path), file_path.stat().st_size
        )

        await _extract_local_data(state)

        if state.data.get("isbn"):
            existing_isbn = await db.find_book_by_isbn(pool, state.data["isbn"])
            if existing_isbn:
                state.final_status = "duplicate_isbn"
        
        await _enrich_data_from_apis(state, use_n8n_test, http_client)
        
        _finalize_processing(state)

    except (IOError, Exception) as e:
        logger.exception(f"Erreur critique dans le pipeline pour {file_path.name}")
        state.final_status = "failed"
        state.error_message = str(e)

    finally:
        end_time = datetime.datetime.now(datetime.timezone.utc)
        state.data["status"] = state.final_status
        state.data["error_message"] = state.error_message
        state.data["processing_completed_at"] = end_time
        state.data["processing_time_ms"] = int((end_time - start_time).total_seconds() * 1000)
        
        if state.book_id:
            await db.update_book_entry(pool, state.book_id, state.data)
    
    return state
