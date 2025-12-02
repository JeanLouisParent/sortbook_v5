"""
HTTP clients for calling external enrichment workflows (N8N, Flowise).
"""
import logging
from typing import Dict, Any, Optional

import httpx

from src.config import Settings

logger = logging.getLogger(__name__)

# --- N8N Clients ---

async def call_n8n_isbn_workflow(
    isbn: str,
    settings: Settings,
    test_mode: bool = False,
    http_client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """
    Calls the N8N webhook to enrich data from an ISBN.
    """
    base_url = settings.n8n_test_base_url if test_mode else settings.n8n_base_url
    path = settings.n8n_test_isbn_path if test_mode else settings.n8n_isbn_path
    url = f"{base_url}{path}"
    
    payload = {"isbn": isbn}
    
    logger.debug(f"Calling N8N ISBN workflow: {url} with ISBN {isbn}")

    try:
        client = http_client or httpx.AsyncClient(timeout=settings.request_timeout)
        response = await client.post(url, json=payload)
        response.raise_for_status()
        
        result = response.json()
        logger.debug(f"N8N ISBN response for {isbn}: {result}")
        return {"data": result}
    
    except httpx.HTTPStatusError as e:
        error_message = f"N8N ISBN HTTP Error: {e.response.status_code} - {e.response.text}"
        logger.error(error_message)
        return {"error": error_message}
    except httpx.RequestError as e:
        error_message = f"Network error calling N8N ISBN: {e}"
        logger.error(error_message)
        return {"error": error_message}
    finally:
        if not http_client and 'client' in locals() and not client.is_closed:
            await client.aclose()


async def call_n8n_metadata_workflow(
    metadata: Dict[str, Any],
    settings: Settings,
    test_mode: bool = False,
    http_client: Optional[httpx.AsyncClient] = None,
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
    
    logger.debug(f"Calling N8N Metadata workflow: {url} with {payload}")

    try:
        client = http_client or httpx.AsyncClient(timeout=settings.request_timeout)
        response = await client.post(url, json=payload)
        response.raise_for_status()
        
        result = response.json()
        logger.debug(f"N8N Metadata response: {result}")
        return {"data": result}

    except httpx.HTTPStatusError as e:
        error_message = f"N8N Metadata HTTP Error: {e.response.status_code} - {e.response.text}"
        logger.error(error_message)
        return {"error": error_message}
    except httpx.RequestError as e:
        error_message = f"Network error calling N8N Metadata: {e}"
        logger.error(error_.message)
        return {"error": error_message}
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

        result = response.json()
        logger.debug(f"Flowise Check response: {result}")
        return {"data": result}

    except httpx.HTTPStatusError as e:
        error_message = f"Flowise Check HTTP Error: {e.response.status_code} - {e.response.text}"
        logger.error(error_message)
        return {"error": error_message}
    except httpx.RequestError as e:
        error_message = f"Network error calling Flowise Check: {e}"
        logger.error(error_message)
        return {"error": error_message}
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

        result = response.json()
        logger.debug(f"Flowise Cover response: {result}")
        return {"data": result}

    except httpx.HTTPStatusError as e:
        error_message = f"Flowise Cover HTTP Error: {e.response.status_code} - {e.response.text}"
        logger.error(error_message)
        return {"error": error_message}
    except httpx.RequestError as e:
        error_message = f"Network error calling Flowise Cover: {e}"
        logger.error(error_message)
        return {"error": error_message}
    finally:
        if not http_client and 'client' in locals() and not client.is_closed:
            await client.aclose()
