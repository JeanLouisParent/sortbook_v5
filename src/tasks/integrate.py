"""
HTTP clients for calling external enrichment workflows (N8N, Flowise).
"""
import logging
from typing import Dict, Any, Optional, List

import httpx

from src.config import Settings

logger = logging.getLogger(__name__)


def _build_error_response(source: str, message: str, raw: Optional[Any] = None) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "success": False,
        "source": source,
        "payload": {},
        "errors": [message],
    }
    if raw is not None:
        response["raw"] = raw
    return response


def _validate_workflow_response(result: Any, expected_source: str) -> Dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("Workflow response must be a JSON object")
    if "success" not in result or "source" not in result:
        raise ValueError("Workflow response must include 'success' and 'source'")
    success = result["success"]
    source = result["source"]
    if not isinstance(success, bool):
        raise ValueError("'success' must be a boolean")
    if not isinstance(source, str):
        raise ValueError("'source' must be a string")
    if source != expected_source:
        raise ValueError(f"Unexpected 'source' value: expected '{expected_source}', got '{source}'")
    payload = result.get("payload")
    if success:
        if not isinstance(payload, dict):
            raise ValueError("Successful workflow response must include a 'payload' object")
        title = payload.get("title")
        author = payload.get("author")
        if not title or not author:
            raise ValueError("Successful workflow response must include 'payload.title' and 'payload.author'")
    elif payload is not None and not isinstance(payload, dict):
        raise ValueError("'payload' must be an object when provided")
    errors = result.get("errors")
    if errors is None:
        result["errors"] = []
    elif not isinstance(errors, list):
        raise ValueError("'errors' must be an array when provided")
    return result

# --- N8N Clients ---

async def call_n8n_isbn_workflow(
    isbn: str,
    settings: Settings,
    test_mode: bool = False,
    http_client: Optional[httpx.AsyncClient] = None,
    metadata: Optional[Dict[str, Any]] = None,
    source_filename: Optional[str] = None,
    isbn_candidates: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Calls the N8N webhook to enrich data from an ISBN.
    """
    base_url = settings.n8n_test_base_url if test_mode else settings.n8n_base_url
    path = settings.n8n_test_isbn_path if test_mode else settings.n8n_isbn_path
    url = f"{base_url}{path}"
    
    payload: Dict[str, Any] = {
        "isbn": isbn,
        "metadata": metadata or {},
        "isbn_candidates": isbn_candidates or [],
    }
    if source_filename:
        payload["filename"] = source_filename
    
    logger.debug(f"Calling N8N ISBN workflow: {url} with ISBN {isbn}")

    try:
        client = http_client or httpx.AsyncClient(timeout=settings.request_timeout, verify=settings.n8n_verify_ssl)
        response = await client.post(url, json=payload)
        response.raise_for_status()
        raw_result = response.json()
        parsed = _validate_workflow_response(raw_result, "n8n_isbn")
        logger.debug(f"N8N ISBN response for {isbn}: {parsed}")
        return parsed

    except ValueError as e:
        logger.error(f"Invalid response from N8N ISBN workflow: {e}")
        return _build_error_response("n8n_isbn", str(e), raw_result if 'raw_result' in locals() else None)
    
    except httpx.HTTPStatusError as e:
        error_message = f"N8N ISBN HTTP Error: {e.response.status_code} - {e.response.text}"
        logger.error(error_message)
        return _build_error_response("n8n_isbn", error_message)
    except httpx.RequestError as e:
        error_message = f"Network error calling N8N ISBN: {e}"
        logger.error(error_message)
        return _build_error_response("n8n_isbn", error_message)
    finally:
        if not http_client and 'client' in locals() and not client.is_closed:
            await client.aclose()


async def call_n8n_metadata_workflow(
    metadata: Dict[str, Any],
    settings: Settings,
    test_mode: bool = False,
    http_client: Optional[httpx.AsyncClient] = None,
    source_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calls the N8N webhook to enrich data from metadata.
    """
    base_url = settings.n8n_test_base_url if test_mode else settings.n8n_base_url
    path = settings.n8n_test_metadata_path if test_mode else settings.n8n_metadata_path
    url = f"{base_url}{path}"
    
    payload = {
        "title": metadata.get("title"),
        "author": metadata.get("creator"),
    }
    if source_filename:
        payload["filename"] = source_filename
    
    logger.debug(f"Calling N8N Metadata workflow: {url} with {payload}")

    try:
        client = http_client or httpx.AsyncClient(timeout=settings.request_timeout, verify=settings.n8n_verify_ssl)
        response = await client.post(url, json=payload)
        response.raise_for_status()
        raw_result = response.json()
        parsed = _validate_workflow_response(raw_result, "n8n_metadata")
        logger.debug(f"N8N Metadata response: {parsed}")
        return parsed

    except ValueError as e:
        logger.error(f"Invalid response from N8N Metadata workflow: {e}")
        return _build_error_response("n8n_metadata", str(e), raw_result if 'raw_result' in locals() else None)

    except httpx.HTTPStatusError as e:
        error_message = f"N8N Metadata HTTP Error: {e.response.status_code} - {e.response.text}"
        logger.error(error_message)
        return _build_error_response("n8n_metadata", error_message)
    except httpx.RequestError as e:
        error_message = f"Network error calling N8N Metadata: {e}"
        logger.error(error_message)
        return _build_error_response("n8n_metadata", error_message)
    finally:
        if not http_client and 'client' in locals() and not client.is_closed:
            await client.aclose()

# --- Flowise Clients ---

async def call_flowise_check_workflow(
    collected_data: Dict[str, Any],
    settings: Settings,
    test_mode: bool = False,
    http_client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """
    Calls the Flowise webhook for a final consistency check.
    """
    base_url = settings.flowise_test_base_url if test_mode else settings.flowise_base_url
    flow_id = settings.flowise_test_check_id if test_mode else settings.flowise_check_id
    url = f"{base_url}/api/v1/prediction/{flow_id}"

    question = f"""
    Here is the data collected for a book:
    - Title from metadata: {collected_data.get('meta_title')}
    - Author from metadata: {collected_data.get('meta_author')}
    - Title from ISBN: {collected_data.get('isbn_title')}
    - Author from ISBN: {collected_data.get('isbn_author')}
    
    Can you give me the most likely title and author in a JSON format {{"title": "...", "author": "..."}}?
    """
    
    payload = {"question": question}
    logger.debug(f"Calling Flowise Check workflow: {url}")

    try:
        client = http_client or httpx.AsyncClient(timeout=settings.request_timeout)
        response = await client.post(url, json=payload)
        response.raise_for_status()

        raw_result = response.json()
        parsed = _validate_workflow_response(raw_result, "flowise_check")
        logger.debug(f"Flowise Check response: {parsed}")
        return parsed

    except ValueError as e:
        logger.error(f"Invalid response from Flowise Check workflow: {e}")
        return _build_error_response("flowise_check", str(e), raw_result if 'raw_result' in locals() else None)

    except httpx.HTTPStatusError as e:
        error_message = f"Flowise Check HTTP Error: {e.response.status_code} - {e.response.text}"
        logger.error(error_message)
        return _build_error_response("flowise_check", error_message)
    except httpx.RequestError as e:
        error_message = f"Network error calling Flowise Check: {e}"
        logger.error(error_message)
        return _build_error_response("flowise_check", error_message)
    finally:
        if not http_client and 'client' in locals() and not client.is_closed:
            await client.aclose()


async def call_flowise_cover_workflow(
    cover_content: bytes,
    settings: Settings,
    test_mode: bool = False,
    http_client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """
    Calls the Flowise webhook for cover image analysis.
    """
    base_url = settings.flowise_test_base_url if test_mode else settings.flowise_base_url
    flow_id = settings.flowise_test_cover_id if test_mode else settings.flowise_cover_id
    url = f"{base_url}/api/v1/prediction/{flow_id}"

    payload = {
        "question": "Analyze this book cover. Extract the title and author.",
    }

    logger.debug(f"Calling Flowise Cover workflow: {url}")

    try:
        files = {'file': ('cover.jpg', cover_content, 'image/jpeg')}
        
        client = http_client or httpx.AsyncClient(timeout=settings.request_timeout)
        response = await client.post(url, data=payload, files=files)
        response.raise_for_status()

        raw_result = response.json()
        parsed = _validate_workflow_response(raw_result, "flowise_cover")
        logger.debug(f"Flowise Cover response: {parsed}")
        return parsed

    except ValueError as e:
        logger.error(f"Invalid response from Flowise Cover workflow: {e}")
        return _build_error_response("flowise_cover", str(e), raw_result if 'raw_result' in locals() else None)

    except httpx.HTTPStatusError as e:
        error_message = f"Flowise Cover HTTP Error: {e.response.status_code} - {e.response.text}"
        logger.error(error_message)
        return _build_error_response("flowise_cover", error_message)
    except httpx.RequestError as e:
        error_message = f"Network error calling Flowise Cover: {e}"
        logger.error(error_message)
        return _build_error_response("flowise_cover", error_message)
    finally:
        if not http_client and 'client' in locals() and not client.is_closed:
            await client.aclose()
