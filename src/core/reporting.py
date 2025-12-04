"""
Functions for reporting the results of the pipeline processing.
"""
from typing import Dict, Any, Optional

def workflow_has_payload(entry: Optional[Dict[str, Any]]) -> bool:
    """Checks if a workflow response dictionary has a successful payload."""
    return bool(
        isinstance(entry, dict)
        and entry.get("success")
        and isinstance(entry.get("payload"), dict)
    )

def has_any_metadata(result: Dict[str, Any]) -> bool:
    """Checks if the result dictionary contains any form of metadata."""
    if workflow_has_payload(result.get("json_n8n_isbn")):
        return True
    if workflow_has_payload(result.get("json_n8n_metadata")):
        return True
    
    extract_metadata = result.get("json_extract_metadata", {}).get("metadata")
    return bool(extract_metadata)

def format_file_line(
    filename: str,
    has_isbn: bool,
    has_metadata: bool,
    processed: bool,
    process_origin: str,
) -> str:
    """Formats a single line of output for a processed file."""
    def _label(value: bool) -> str:
        return "oui" if value else "non"

    origin = process_origin or "inconnu"
    return (
        f"{filename} | isbn={_label(has_isbn)} | metadata={_label(has_metadata)} | "
        f"traité={_label(processed)} | par={origin}"
    )
