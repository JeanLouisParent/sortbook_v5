"""
HTTP client for the single SortBook n8n workflow.
"""
from typing import Any, Dict, Optional, Tuple
import logging

import httpx

from src.config import Settings

logger = logging.getLogger(__name__)


def _build_error_response(source: str, message: str, raw: Optional[Any] = None) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "success": False,
        "source": source,
        "payload": None,
        "errors": [message],
    }
    if raw is not None:
        response["raw"] = raw
    return response


def _validate_workflow_response(result: Any, expected_source: Optional[str] = None) -> Dict[str, Any]:
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
    if expected_source and source != expected_source:
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


def _ensure_dict_response(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, dict):
            return first
    raise ValueError("Workflow response must be a JSON object")


async def call_n8n_sortebook_workflow(
    payload: Dict[str, Any],
    settings: Settings,
    test_mode: bool = False,
    http_client: Optional[httpx.AsyncClient] = None,
) -> Tuple[Dict[str, Any], Any]:
    """
    Calls the n8n workflow that finalizes the SortBook pipeline.
    """
    url = settings.n8n_test_workflow_url if test_mode else settings.n8n_workflow_url

    logger.debug("Calling SortBook n8n workflow: %s", url)

    try:
        client = http_client or httpx.AsyncClient(
            timeout=settings.request_timeout, verify=settings.n8n_verify_ssl
        )
        response = await client.post(url, json=payload)
        response.raise_for_status()
        raw_result = response.json()
        normalized = _ensure_dict_response(raw_result)
        parsed = _validate_workflow_response(normalized)
        logger.debug("SortBook workflow response: %s", parsed)
        return parsed, raw_result

    except ValueError as e:
        logger.error("Invalid response from SortBook workflow: %s", e)
        return _build_error_response("sortebook_v5", str(e), raw_result if 'raw_result' in locals() else None), raw_result if 'raw_result' in locals() else None
    except httpx.HTTPStatusError as e:
        error_message = f"SortBook workflow HTTP Error: {e.response.status_code} - {e.response.text}"
        logger.error(error_message)
        return _build_error_response("sortebook_v5", error_message), None
    except httpx.RequestError as e:
        error_message = f"Network error calling SortBook workflow: {e}"
        logger.error(error_message)
        return _build_error_response("sortebook_v5", error_message), None
    finally:
        if not http_client and 'client' in locals() and not client.is_closed:
            await client.aclose()
