"""
Contextual Indexing Engine (Step 10).
Prepends verified deterministic document, section, and entity context to searchable passages.
Maintains clear boundaries between verified source facts and contextual prefixes.
"""

from typing import List, Optional
from backend.src.schemas.contracts import (
    DocumentRegion,
    LogicalDocument,
    LogicalSection,
)


class ContextualIndexer:
    """
    Constructs context-enriched representations for passage retrieval (Anthropic style),
    ensuring that isolated chunks maintain unambiguous document and section provenance.
    """

    @classmethod
    def create_contextual_prefix(
        cls,
        doc_title: str,
        section_path: Optional[str] = None,
        key_identifiers: Optional[List[str]] = None,
        is_generated: bool = False,
        table_title: Optional[str] = None,
        unit: Optional[str] = None,
        include_provenance_tag: bool = False,
    ) -> str:
        """
        Creates a structured, deterministic contextual envelope prefix.
        Avoids blanket [Verified Provenance] label (traceable metadata is not automatically verified).
        Scopes identifiers locally.
        Deterministic format:
        Document: Annual Report 2024 | Section: Financial Statements → Revenue | Table: Revenue by Segment | Unit: USD millions
        """
        parts = [f"Document: {doc_title}"]
        if section_path:
            parts.append(f"Section: {section_path}")
        if table_title:
            parts.append(f"Table: {table_title}")
        if unit:
            parts.append(f"Unit: {unit}")
        if key_identifiers:
            clean_ids = [i for i in key_identifiers if len(i) < 30][:4]
            if clean_ids:
                parts.append(f"Identifiers: {', '.join(clean_ids)}")

        prefix = " | ".join(parts)
        if is_generated:
            return f"[Generated Context] {prefix}\n\n"
        if include_provenance_tag:
            return f"[Verified Provenance] {prefix}\n\n"
        return f"{prefix}\n\n"

    @classmethod
    def enrich_region_with_context(
        cls,
        region: DocumentRegion,
        doc_title: str,
        section_path: Optional[str] = None,
        table_title: Optional[str] = None,
        unit: Optional[str] = None,
        include_provenance_tag: bool = False,
    ) -> str:
        """
        Returns the context-prefixed text representation for indexing into Qdrant / BM25.
        Uses local_identifiers when available to prevent cross-chunk false matches.
        """
        local_ids = region.local_identifiers if region.local_identifiers else region.identifiers
        prefix = cls.create_contextual_prefix(
            doc_title=doc_title,
            section_path=section_path,
            key_identifiers=local_ids,
            is_generated=bool(region.generated_context),
            table_title=table_title,
            unit=unit,
            include_provenance_tag=include_provenance_tag,
        )
        return prefix + (region.source_text or region.text)

