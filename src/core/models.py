"""
Pydantic models for data structures used in the pipeline.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class BaseWorkflowPayload(BaseModel):
    """Base model for a workflow payload, requiring title and author."""
    title: str
    author: str

class WorkflowResponse(BaseModel):
    """
    Represents the standardized response from an external workflow (N8N, Flowise).
    """
    success: bool
    source: str
    payload: Optional[BaseWorkflowPayload] = None
    errors: List[str] = []
    raw: Optional[Dict[str, Any]] = None

class ExtractedMetadata(BaseModel):
    """EPUB metadata extracted by ebooklib."""
    title: Optional[Any] = None
    creator: Optional[Any] = None
    publisher: Optional[Any] = None
    date: Optional[Any] = None
    identifier: Optional[Any] = None
    language: Optional[Any] = None
    description: Optional[Any] = None
    subjects: Optional[Any] = None

class ExtractionResult(BaseModel):
    """Result of a single extraction task."""
    metadata: Optional[ExtractedMetadata] = None
    error: Optional[str] = None

class IsbnData(BaseModel):
    isbn: Optional[str] = None
    isbn_source: str = "none"
    all_isbns: List[str] = []
    isbn_candidates: List[str] = []
    error: Optional[str] = None

class CoverData(BaseModel):
    has_cover: bool = False
    cover_filename: Optional[str] = None
    cover_media_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    format: Optional[str] = None
    error: Optional[str] = None
    cover_content: Optional[bytes] = None # This will be excluded from serialization

    class Config:
        arbitrary_types_allowed = True
        exclude = {"cover_content"}

class TextPreviewData(BaseModel):
    text_preview: Optional[str] = None
    extracted_chars: int = 0
    language: Optional[str] = None
    error: Optional[str] = None
