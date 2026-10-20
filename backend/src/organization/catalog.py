"""
Faceted Catalog & Indexed Filters Engine (Step 12).
Builds structured facet catalogs for browsing and targeted Qdrant pre-filtering.
"""

from typing import List, Optional
from backend.src.schemas.contracts import (
    DocumentTypeLabel,
    DomainLabel,
    FacetedCatalogRecord,
    QualityState,
    StructuredDocument,
)


class CatalogManager:
    """
    Builds and manages indexed facet filters for fast metadata search and browsing.
    """

    @classmethod
    def generate_faceted_record(
        cls,
        doc_id: str,
        version_id: str,
        title: str,
        domains: List[DomainLabel],
        doc_types: List[DocumentTypeLabel],
        organizations: List[str],
        identifiers: List[str],
        effective_date: Optional[str] = None,
        quality_state: QualityState = QualityState.READABLE,
    ) -> FacetedCatalogRecord:
        """
        Creates a FacetedCatalogRecord for catalog indexing.
        """
        return FacetedCatalogRecord(
            document_id=doc_id,
            version_id=version_id,
            title=title,
            domains=[d.value if hasattr(d, "value") else str(d) for d in domains],
            document_types=[t.value if hasattr(t, "value") else str(t) for t in doc_types],
            organizations=organizations,
            identifiers=identifiers[:10],
            effective_date=effective_date,
            quality_state=quality_state,
        )
