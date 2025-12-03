"""
Orchestration du pipeline de traitement pour un seul fichier EPUB.
"""
import asyncio
import datetime
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import httpx
from asyncpg.pool import Pool

from src.config import Settings
from src.db import database as db
from src.tasks import extract, integrate

logger = logging.getLogger(__name__)

def _workflow_payload(response: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if response and response.get("success"):
        payload = response.get("payload", {})
        if isinstance(payload, dict):
            return payload
    return None

class PipelineState:
    """Contient l'état et les données collectées pour un fichier."""
    def __init__(self, file_path: Path, settings: Settings):
        self.file_path = file_path
        self.settings = settings
        self.book_id: Optional[str] = None
        self.data: Dict[str, Any] = {}
        self.final_status: str = "pending"
        self.error_message: Optional[str] = None

def _choose_final_data(state: PipelineState) -> Tuple[str, str, str]:
    """Logique de décision pour choisir le titre/auteur final à partir des workflows externes."""
    # Priorité 1: Résultats du workflow N8N ISBN
    isbn_payload = _workflow_payload(state.data.get("json_n8n_isbn"))
    if isbn_payload:
        title = isbn_payload.get("title")
        author = isbn_payload.get("author")
        if title and author:
            logger.debug(f"Choix final pour {state.file_path.name}: N8N ISBN")
            return title, author, "isbn"

    metadata_payload = _workflow_payload(state.data.get("json_n8n_metadata"))
    if metadata_payload:
        title = metadata_payload.get("title")
        author = metadata_payload.get("author")
        if title and author:
            logger.debug(f"Choix final pour {state.file_path.name}: N8N metadata workflow")
            return title, author, "n8n_metadata"

    # TODO: Ajouter d'autres logiques (Flowise, etc.) dès qu'elles seront disponibles.

    logger.warning(f"Impossible de déterminer un titre/auteur pour {state.file_path.name}")
    return "Unknown", "Unknown", "unknown"

async def run_pipeline(
    file_path: Path,
    pool: Pool,
    settings: Settings,
    dry_run: bool,
    test_mode: bool,
    use_n8n_test: bool,
    http_client: httpx.AsyncClient,
):
    """
    Exécute le pipeline complet pour un fichier EPUB.
    """
    start_time = datetime.datetime.now(datetime.timezone.utc)
    state = PipelineState(file_path, settings)
    
    try:
        # 1. Préparation / Hash
        state.data["file_hash"] = extract.get_file_hash(file_path)
        
        # 2. Vérification Doublon de Hash
        existing_book = await db.find_book_by_hash(pool, state.data["file_hash"])
        if existing_book:
            state.final_status = "duplicate_hash"
            return state.data  # Arrêt anticipé

        # 3. Création de l'entrée en DB
        state.book_id = await db.create_book_entry(
            pool,
            state.data["file_hash"],
            file_path.name,
            str(file_path),
            file_path.stat().st_size,
        )

        # 4. Extraction locale
        state.data["json_extract_metadata"] = extract.extract_epub_metadata(file_path)
        state.data["epub_metadata"] = state.data["json_extract_metadata"]
        state.data["json_extract_isbn"] = extract.extract_isbn(file_path)
        text_data = extract.extract_text_preview(file_path, settings.text_preview_chars)
        state.data["json_extract_text"] = text_data
        state.data["text_preview"] = text_data.get("text_preview")
        
        cover_data = extract.extract_cover(file_path)
        state.data["has_cover"] = cover_data["has_cover"]
        state.data["json_extract_cover"] = {k: v for k, v in cover_data.items() if k != 'cover_content'}
        
        # 5. Vérification Doublon ISBN
        isbn_info = state.data["json_extract_isbn"]
        if isbn_info.get("isbn"):
            state.data["isbn"] = isbn_info["isbn"]
            state.data["isbn_source"] = isbn_info["isbn_source"]
            state.data["isbn_candidates"] = isbn_info.get("isbn_candidates") or isbn_info.get("all_isbns") or []
            existing_isbn = await db.find_book_by_isbn(pool, isbn_info["isbn"])
            if existing_isbn:
                state.final_status = "duplicate_isbn"
                # On continue pour enregistrer les métadonnées, mais sans appeler les APIs
                
        # 6. Appels API (si non doublon)
        if state.final_status not in ["duplicate_hash", "duplicate_isbn"]:
            metadata_payload = state.data.get("json_extract_metadata", {}).get("metadata")
            isbn_candidates = state.data.get("isbn_candidates") or isbn_info.get("all_isbns", [])
            metadata_should_run = False
            isbn_response = None
            if state.data.get("isbn"):
                isbn_response = await integrate.call_n8n_isbn_workflow(
                    state.data["isbn"],
                    settings,
                    use_n8n_test,
                    http_client,
                    metadata=metadata_payload,
                    source_filename=file_path.name,
                    isbn_candidates=isbn_candidates,
                )
                state.data["json_n8n_isbn"] = isbn_response
                metadata_should_run = not _workflow_payload(isbn_response)
            else:
                metadata_should_run = True  # Pas d'ISBN : on se replie sur metadata

            if metadata_payload and metadata_should_run:
                metadata_response = await integrate.call_n8n_metadata_workflow(
                    metadata_payload, settings, use_n8n_test, http_client, file_path.name
                )
                state.data["json_n8n_metadata"] = metadata_response
            # Ajouter d'autres appels (metadata, flowise) ici si nécessaire...
            # Exemple:
            # if state.data["has_cover"] and cover_data.get("cover_content"):
            #     state.data["json_flowise_cover"] = await flowise_cover.call_flowise_cover_workflow(...)

        # 7. Choix final
        final_title, final_author, choice_source = _choose_final_data(state)
        state.data["final_title"] = final_title
        state.data["final_author"] = final_author
        state.data["choice_source"] = choice_source
        
        if choice_source != "unknown":
            if state.final_status == "pending": # Ne pas écraser 'duplicate_isbn'
                state.final_status = "processed"
        else:
            state.final_status = "failed"
            state.error_message = "Impossible de déterminer le titre/auteur."

    except Exception as e:
        logger.exception(f"Erreur critique dans le pipeline pour {file_path.name}")
        state.final_status = "failed"
        state.error_message = str(e)

    finally:
        # 8. Mise à jour finale en DB
        end_time = datetime.datetime.now(datetime.timezone.utc)
        state.data["status"] = state.final_status
        state.data["error_message"] = state.error_message
        state.data["processing_completed_at"] = end_time
        state.data["processing_time_ms"] = int((end_time - start_time).total_seconds() * 1000)
        
        # Convertir les objets non sérialisables
        for key, value in state.data.items():
            if isinstance(value, dict):
                 # Retirer le contenu binaire de la cover avant de stocker en JSON
                if key == "json_extract_cover" and "cover_content" in value:
                    del value["cover_content"]

        if state.book_id:
            await db.update_book_entry(pool, state.book_id, state.data)
        
    # 9. Déplacement de fichier (stub)
    # if not dry_run:
    #     move_file(file_path, state.final_status, settings)
    
    return state.data
