"""
Exact Identifier Lookup Engine.
Provides deterministic, strict constraint matching for technical identifiers
(lot numbers, ECN codes, part numbers, drawing IDs, revisions).
Separates exact identity validation from relevance ranking.
"""

import re
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.src.schemas.contracts import (
    BoundingBox,
    DocumentRegion,
    ExtractionMethod,
    QualityStatus,
    StructuredDocument,
)


class IdentifierRecord(BaseModel):
    """Normalized record for an exact technical identifier."""
    original_value: str
    normalized_value: str
    identifier_type: str  # e.g., 'lot_number', 'ecn_code', 'part_number'
    doc_id: str
    version_id: str
    page_number: int
    element_id: str
    box_2d: Optional[BoundingBox] = None
    extraction_status: QualityStatus = QualityStatus.VERIFIED


class ExactLookupResult(BaseModel):
    """Result of an exact identifier search."""
    query_identifier: str
    has_exact_match: bool
    matched_records: List[IdentifierRecord] = Field(default_factory=list)
    approximate_suggestions: List[str] = Field(default_factory=list)
    message: str = ""


class ExactIdentifierLookup:
    """
    Inverted exact lookup index preserving leading zeros, meaningful punctuation,
    and distinct identifier types.
    """

    def __init__(self):
        # normalized_value -> List[IdentifierRecord]
        self._index: Dict[str, List[IdentifierRecord]] = {}
        # original_value -> List[IdentifierRecord]
        self._exact_case_index: Dict[str, List[IdentifierRecord]] = {}

    @staticmethod
    def normalize_identifier(raw_id: str) -> str:
        """
        Normalizes an identifier for matching while strictly preserving
        leading zeros, hyphens, and essential punctuation.
        Does NOT equate AB-01 with AB01 unless authorized.
        """
        if not raw_id:
            return ""
        # Strip outer whitespace and uppercase
        cleaned = raw_id.strip().upper()
        # Remove multiple consecutive internal spaces
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    @staticmethod
    def detect_identifier_type(raw_id: str) -> str:
        """Classifies the identifier format."""
        upper = raw_id.upper()
        if "ECN-" in upper:
            return "ecn_code"
        if re.search(r"\bLOT\b|\bBATCH\b|[0-9]{7,10}", upper):
            return "lot_number"
        if re.search(r"\bPART\b|\bCAT\b|\bREF\b|[A-Z]{2,4}-[0-9]{3,6}", upper):
            return "part_number"
        if re.search(r"\bREV\b|\bREVISION\b", upper):
            return "revision_code"
        return "general_code"

    def index_document(self, structured_doc: StructuredDocument):
        """Extracts and indexes all identifiers from regions and metadata."""
        doc_id = structured_doc.document_id
        version_id = structured_doc.version_id

        for reg in structured_doc.regions:
            # Check local_identifiers and identifiers
            all_ids = set(reg.local_identifiers + reg.identifiers)

            # Also check text for common identifier patterns
            ecns = re.findall(r"\bECN-[0-9]{4}-[0-9]{3,5}\b", reg.text, re.IGNORECASE)
            lots = re.findall(r"\b(?:lot|batch)\s*(?:no\.?|#|number)?\s*[:\-]?\s*([A-Za-z0-9\-]+)", reg.text, re.IGNORECASE)
            for e in ecns + lots:
                if len(e.strip()) < 30:
                    all_ids.add(e.strip())

            STOP_CODES = {"number", "numbers", "code", "codes", "id", "item", "the", "for", "rev", "page", "lot", "batch"}
            for raw_val in all_ids:
                if not raw_val or len(raw_val) < 2 or raw_val.lower() in STOP_CODES:
                    continue
                norm_val = self.normalize_identifier(raw_val)
                id_type = self.detect_identifier_type(raw_val)

                rec = IdentifierRecord(
                    original_value=raw_val,
                    normalized_value=norm_val,
                    identifier_type=id_type,
                    doc_id=doc_id,
                    version_id=version_id,
                    page_number=reg.page_number,
                    element_id=reg.region_id,
                    box_2d=reg.box_2d,
                    extraction_status=reg.quality_status,
                )

                if norm_val not in self._index:
                    self._index[norm_val] = []
                self._index[norm_val].append(rec)

                if raw_val not in self._exact_case_index:
                    self._exact_case_index[raw_val] = []
                self._exact_case_index[raw_val].append(rec)

    def lookup(
        self,
        query: str,
        doc_id: Optional[str] = None,
        version_id: Optional[str] = None,
        match_case: bool = False,
    ) -> ExactLookupResult:
        """
        Executes a deterministic constraint lookup for an exact identifier.
        If no exact match exists, reports that fact clearly and computes approximate suggestions.
        """
        raw_query = query.strip()
        norm_query = self.normalize_identifier(raw_query)

        candidates = self._exact_case_index.get(raw_query, []) if match_case else self._index.get(norm_query, [])

        if not candidates and not match_case:
            # Check without 'LOT' or 'BATCH' label prefix
            stripped = re.sub(r"^(?:LOT|BATCH)\s*(?:NO\.?|#)?\s*[:\-]?\s*", "", norm_query).strip()
            if stripped and stripped in self._index:
                candidates = self._index[stripped]

        # Filter by doc_id / version_id if specified
        if doc_id:
            candidates = [c for c in candidates if c.doc_id == doc_id]
        if version_id:
            candidates = [c for c in candidates if c.version_id == version_id]

        if candidates:
            return ExactLookupResult(
                query_identifier=raw_query,
                has_exact_match=True,
                matched_records=candidates,
                approximate_suggestions=[],
                message=f"Found {len(candidates)} exact match(es) for identifier '{raw_query}'.",
            )

        # No exact match: find approximate lexical suggestions (e.g. edit distance or prefix)
        suggestions = []
        for indexed_val in self._index.keys():
            if norm_query in indexed_val or indexed_val in norm_query:
                suggestions.append(indexed_val)
            elif len(norm_query) > 4 and indexed_val[:4] == norm_query[:4]:
                suggestions.append(indexed_val)

        return ExactLookupResult(
            query_identifier=raw_query,
            has_exact_match=False,
            matched_records=[],
            approximate_suggestions=sorted(list(set(suggestions)))[:5],
            message=f"No exact match found for identifier '{raw_query}'.",
        )
