"""
HTTP clients for calling external enrichment workflows (N8N, Flowise).
"""
import logging
from typing import Dict, Any, Optional, List

import httpx
from pydantic import ValidationError

from src.config import Settings
from src.core.models import WorkflowResponse

logger = logging.getLogger(__name__)


def _build_error_response(source: str, message: str, raw: Optional[Any] = None) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "success": False, "source": source, "payload": {}, "errors": [message]
    }
    if raw is not None:
        response["raw"] = raw
    return response


def _validate_workflow_response(result: Dict[str, Any], expected_source: str) -> Dict[str, Any]:
    """Parses and validates the workflow response using Pydantic models."""
    response_model = WorkflowResponse.model_validate(result)
    if response_model.source != expected_source:
        raise ValueError(f"Unexpected 'source': expected '{expected_source}', got '{response_model.source}'")
    return response_model.model_dump()


async def _call_workflow(
    http_client: httpx.AsyncClient,
    url: str,
    payload: Dict[str, Any],
    source: str,
    files: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generic function to call a workflow, handle errors, and validate response."""
    logger.debug(f"Calling {source} workflow at {url}")
    raw_result = None
    try:
        response = await http_client.post(url, json=payload if not files else None, data=payload if files else None, files=files)
        response.raise_for_status()
        raw_result = response.json()
        return _validate_workflow_response(raw_result, source)
    except (ValidationError, ValueError) as e:
        logger.error(f"Invalid response from {source}: {e}")
        return _build_error_response(source, str(e), raw_result)
    except httpx.HTTPStatusError as e:
        msg = f"HTTP Error {e.response.status_code}: {e.response.text}"
        logger.error(f"Error calling {source}: {msg}")
        return _build_error_response(source, msg)
    except httpx.RequestError as e:
        msg = f"Network error calling {source}: {e}"
        logger.error(msg)
        return _build_error_response(source, msg)

# --- N8N Clients ---

async def call_n8n_isbn_workflow(
    isbn: str,
    settings: Settings,
    use_n8n_test: bool,
    http_client: httpx.AsyncClient,
    metadata: Optional[Dict[str, Any]] = None,
    source_filename: Optional[str] = None,
    isbn_candidates: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Calls the N8N webhook to enrich data from an ISBN."""
    base_url = settings.n8n_test_base_url if use_n8n_test else settings.n8n_base_url
    path = settings.n8n_test_isbn_path if use_n8n_test else settings.n8n_isbn_path
    url = f"{base_url}{path}"
    
    payload = {"isbn": isbn, "metadata": metadata or {}, "isbn_candidates": isbn_candidates or []}
    if source_filename:
        payload["filename"] = source_filename
    
    return await _call_workflow(http_client, url, payload, "n8n_isbn")

async def call_n8n_metadata_workflow(
    metadata: Dict[str, Any],
    settings: Settings,
    use_n8n_test: bool,
    http_client: httpx.AsyncClient,
    source_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Calls the N8N webhook to enrich data from metadata."""
    base_url = settings.n8n_test_base_url if use_n8n_test else settings.n8n_base_url
    path = settings.n8n_test_metadata_path if use_n8n_test else settings.n8n_metadata_path
    url = f"{base_url}{path}"
    
    payload = {"title": metadata.get("title"), "author": metadata.get("creator")}
    if source_filename:
        payload["filename"] = source_filename
        
    return await _call_workflow(http_client, url, payload, "n8n_metadata")

# --- Flowise Clients ---

async def call_flowise_check_workflow(
    collected_data: Dict[str, Any],
    settings: Settings,
    test_mode: bool,
    http_client: httpx.AsyncClient,
) -> Dict[str, Any]:
    """Calls the Flowise webhook for a final consistency check."""
    base_url = settings.flowise_test_base_url if test_mode else settings.flowise_base_url
    flow_id = settings.flowise_test_check_id if test_mode else settings.flowise_check_id
    url = f"{base_url}/api/v1/prediction/{flow_id}"

    question = f"""
    Data:
    - Metadata Title: {collected_data.get('meta_title')}
    - Metadata Author: {collected_data.get('meta_author')}
    - ISBN Title: {collected_data.get('isbn_title')}
    - ISBN Author: {collected_data.get('isbn_author')}
    Task: Provide the most likely title and author in JSON format {{"title": "...", "author": "..."}}.
    """
    
    payload = {"question": question}
    return await _call_workflow(http_client, url, payload, "flowise_check")

async def call_flowise_cover_workflow(
    cover_content: bytes,
    settings: Settings,
    test_mode: bool,
    http_client: httpx.AsyncClient,
) -> Dict[str, Any]:
    """Calls the Flowise webhook for cover image analysis."""
    base_url = settings.flowise_test_base_url if test_mode else settings.flowise_base_url
    flow_id = settings.flowise_test_cover_id if test_mode else settings.flowise_cover_id
    url = f"{base_url}/api/v1/prediction/{flow_id}"

    payload = {"question": "Analyze this book cover. Extract the title and author."}
    files = {'file': ('cover.jpg', cover_content, 'image/jpeg')}
    
    return await _call_workflow(http_client, url, payload, "flowise_cover", files=files)
