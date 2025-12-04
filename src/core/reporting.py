"""
Helpers for formatting the per-file report that the CLI prints.
"""
from typing import Any, Dict


def has_any_metadata(result: Dict[str, Any]) -> bool:
    """Returns True if we extracted metadata or n8n provided a payload."""
    parsed = result.get("json_n8n_response_parsed", {}) or {}
    n8n_payload = parsed.get("payload")
    if isinstance(n8n_payload, dict) and n8n_payload:
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
