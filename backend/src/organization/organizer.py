"""
Master Document Organization Orchestrator.
Integrates all 12 organization techniques:
1. Logical document separation
2. Hierarchical multi-label classification
3. Section hierarchy reconstruction
4. Parent-child organization
5. Cross-page and cross-element linking
6. Common metadata schema with domain extensions
7. Entity extraction and resolution
8. Temporal and version organization
9. Duplicate and near-duplicate grouping
10. Contextual indexing
11. Provenance and quality organization
12. Faceted catalog generation
"""

from typing import Dict, List, Optional, Tuple
from backend.src.organization.logical_separation import LogicalDocumentSeparator
from backend.src.organization.classifier import MultiLabelClassifier
from backend.src.organization.section_hierarchy import SectionHierarchyBuilder
from backend.src.organization.cross_linker import CrossElementLinker
from backend.src.organization.metadata_engine import MetadataEngine
from backend.src.organization.near_duplicate import DuplicateDetector
from backend.src.organization.contextual_indexer import ContextualIndexer
from backend.src.organization.catalog import CatalogManager
from backend.src.schemas.contracts import (
    ContentRelationship,
    DocumentRegion,
    DomainExtension,
    DomainLabel,
    ExtractedFieldRecord,
    FacetedCatalogRecord,
    LogicalDocument,
    LogicalSection,
    PageMetadata,
    QualityState,
    StructuredTable,
    TemporalRecord,
)


class DocumentOrganizer:
    """
    Coordinates logical document organization, section tree building, cross-element linking,
    and metadata enrichment across physical pages and extracted regions.
    """

    @classmethod
    def organize_document(
        cls,
        doc_id: str,
        version_id: str,
        pages: List[PageMetadata],
        regions: List[DocumentRegion],
        tables: List[StructuredTable],
        page_texts: Dict[int, str],
    ) -> Tuple[
        List[LogicalDocument],
        List[LogicalSection],
        List[ContentRelationship],
        List[ExtractedFieldRecord],
        TemporalRecord,
        DomainExtension,
        FacetedCatalogRecord,
    ]:
        """
        Executes end-to-end logical document organization and evidence mapping.
        """
        full_text = " ".join([page_texts.get(p, "") for p in sorted(page_texts.keys())])

        # 1. Step 1: Logical document separation
        logical_docs = LogicalDocumentSeparator.detect_subdocuments(
            pages=pages,
            page_texts=page_texts,
            doc_id=doc_id,
        )

        # 2. Step 2: Multi-label classification
        domains = MultiLabelClassifier.classify_domains(full_text)
        doc_type = MultiLabelClassifier.classify_document_type(full_text, pages)
        for ldoc in logical_docs:
            ldoc.domains = domains
            ldoc.doc_type = doc_type

        # 3. Step 3: Section hierarchy reconstruction
        sections = SectionHierarchyBuilder.build_hierarchy(
            regions=regions,
            logical_docs=logical_docs,
        )

        # 4. Steps 4 & 5: Parent-child and cross-element linking
        table_links = CrossElementLinker.link_table_continuations(tables)
        caption_footnote_links = CrossElementLinker.link_captions_and_footnotes(regions)
        all_relationships = table_links + caption_footnote_links

        # 5. Steps 6, 7 & 8: Metadata, domain extensions, entities, temporal data
        temporal_record = MetadataEngine.extract_temporal_metadata(full_text)
        domain_ext, extracted_fields = MetadataEngine.extract_domain_extension(full_text, domains)
        organizations = MetadataEngine.extract_organizations(full_text)

        # Gather all extracted lot/part identifiers from regions
        all_identifiers = set()
        for r in regions:
            for i in r.identifiers:
                all_identifiers.add(i)

        # 6. Step 10: Contextual Indexing (enriching text regions)
        doc_title = logical_docs[0].title if logical_docs else "Document"
        for r in regions:
            sec_path = None
            if r.parent_section_id:
                for s in sections:
                    if s.section_id == r.parent_section_id:
                        sec_path = s.heading_path
                        break
            # Prepend contextual envelope to text for indexing
            r.text = ContextualIndexer.enrich_region_with_context(
                region=r,
                doc_title=doc_title,
                section_path=sec_path,
            )

        # 7. Step 12: Faceted Catalog Record
        overall_quality = QualityState.READABLE
        if any(p.quality and not p.quality.text_layer_valid for p in pages):
            overall_quality = QualityState.PARTIALLY_UNREADABLE

        catalog_record = CatalogManager.generate_faceted_record(
            doc_id=doc_id,
            version_id=version_id,
            title=doc_title,
            domains=domains,
            doc_types=[doc_type],
            organizations=organizations,
            identifiers=sorted(list(all_identifiers)),
            effective_date=temporal_record.effective_date,
            quality_state=overall_quality,
        )

        return (
            logical_docs,
            sections,
            all_relationships,
            extracted_fields,
            temporal_record,
            domain_ext,
            catalog_record,
        )
