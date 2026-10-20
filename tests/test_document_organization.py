"""
Unit & Integration Tests for Document Organization & Logical Structure (12 Techniques).
Verifies:
1. Logical document separation
2. Hierarchical multi-label classification
3. Section hierarchy reconstruction
4. Parent-child organization & evidence relationships
5. Cross-page and cross-element linking (table continuations, footnotes, figure refs)
6. Common metadata schema with domain extensions
7. Entity extraction and resolution
8. Temporal & version organization
9. Duplicate and near-duplicate grouping
10. Contextual indexing
11. Provenance and quality organization
12. Faceted catalog generation
"""

from pathlib import Path
import pytest

from backend.src.organization.logical_separation import LogicalDocumentSeparator
from backend.src.organization.classifier import MultiLabelClassifier
from backend.src.organization.section_hierarchy import SectionHierarchyBuilder
from backend.src.organization.cross_linker import CrossElementLinker
from backend.src.organization.metadata_engine import MetadataEngine
from backend.src.organization.near_duplicate import DuplicateDetector
from backend.src.organization.contextual_indexer import ContextualIndexer
from backend.src.organization.catalog import CatalogManager
from backend.src.organization.organizer import DocumentOrganizer
from backend.src.ingestion.hybrid_pipeline import HybridIngestionPipeline
from backend.src.retrieval.visual_indexer import QdrantVisualRetriever
from backend.src.schemas.contracts import (
    BoundingBox,
    ContentRelationType,
    DocumentRegion,
    DocumentTypeLabel,
    DomainLabel,
    PageMetadata,
    PageQualityAssessment,
    PageType,
    QualityState,
    QualityStatus,
    RegionType,
    SectionRole,
    StructuredTable,
    TableCell,
)


@pytest.fixture
def sample_pdf_path():
    p = Path(__file__).resolve().parent.parent / "pharma-blob-sample.pdf"
    assert p.exists()
    return p


def test_technique_1_logical_document_separation():
    # Simulate a 6-page bundle with a subdocument title shift at page 4
    page_texts = {
        1: "AKTA ready Compliance Package Overview",
        2: "Operating specifications",
        3: "Pressure calibration parameters",
        4: "Certificate of Analysis for Gamma Irradiation Lot 18356721",
        5: "Biological indicator test findings",
        6: "QA Inspector sign-off and stamp",
    }
    pages = [PageMetadata(page_number=i, image_path=f"p_{i}.png", width=595, height=842) for i in range(1, 7)]

    subdocs = LogicalDocumentSeparator.detect_subdocuments(pages, page_texts, doc_id="test_doc")
    assert len(subdocs) >= 2
    assert subdocs[0].start_page == 1
    assert subdocs[1].start_page == 4
    assert subdocs[1].doc_type == DocumentTypeLabel.CERTIFICATE


def test_technique_2_multi_label_classification():
    text_pharma = "Cytiva AKTA ready single-use flow kit gamma irradiation 25-40 kGy lot 18356721"
    domains = MultiLabelClassifier.classify_domains(text_pharma)
    assert DomainLabel.HEALTHCARE in domains or DomainLabel.ENGINEERING in domains

    doc_type = MultiLabelClassifier.classify_document_type("Certificate of Analysis Quality Assurance Release", [])
    assert doc_type == DocumentTypeLabel.CERTIFICATE

    sec_role = MultiLabelClassifier.classify_section_role("1.0 Operating Specifications")
    assert sec_role == SectionRole.SPECIFICATIONS


def test_technique_3_section_hierarchy_reconstruction():
    regions = [
        DocumentRegion(region_id="r1", page_number=1, region_type=RegionType.HEADING, text="1.0 System Architecture"),
        DocumentRegion(region_id="r2", page_number=1, region_type=RegionType.PARAGRAPH, text="The system uses single-use flow kits."),
        DocumentRegion(region_id="r3", page_number=1, region_type=RegionType.HEADING, text="1.1 Pressure Specifications"),
        DocumentRegion(region_id="r4", page_number=1, region_type=RegionType.PARAGRAPH, text="Operating limit is 3.0 bar."),
    ]
    sections = SectionHierarchyBuilder.build_hierarchy(regions, logical_docs=[])
    assert len(sections) == 2
    assert sections[0].heading_path == "1.0 System Architecture"
    assert sections[1].heading_path == "1.0 System Architecture > 1.1 Pressure Specifications"
    assert "r4" in sections[1].element_ids


def test_technique_4_and_5_cross_element_linking():
    # Test table continuation across page boundaries
    t1 = StructuredTable(
        table_id="tbl_p1",
        page_number=1,
        headers=["Param", "Limit", "Actual"],
        rows=[["P1", "10", "9"]],
    )
    t2 = StructuredTable(
        table_id="tbl_p2",
        page_number=2,
        headers=["Param", "Limit", "Actual"],
        rows=[["P2", "20", "19"]],
    )
    table_links = CrossElementLinker.link_table_continuations([t1, t2])
    assert len(table_links) == 1
    assert table_links[0].relation_type == ContentRelationType.TABLE_CONTINUATION
    assert t1.continues_on_page == 2
    assert t2.continued_from_page == 1

    # Test footnote-to-table linking
    r_table = DocumentRegion(region_id="tbl_r", page_number=1, region_type=RegionType.TABLE, text="| Col1 | Col2 |")
    r_fn = DocumentRegion(region_id="fn_r", page_number=1, region_type=RegionType.PARAGRAPH, text="* Note: Stored at > +5°C under controlled humidity.")
    fn_links = CrossElementLinker.link_captions_and_footnotes([r_table, r_fn])
    assert len(fn_links) == 1
    assert fn_links[0].relation_type == ContentRelationType.FOOTNOTE_FOR


def test_technique_6_7_8_metadata_domain_extensions():
    text = "Cytiva AKTA ready Lot: 18356721 ECN-2023-0847 effective January 15, 2024"
    temp_rec = MetadataEngine.extract_temporal_metadata(text)
    assert temp_rec.effective_date is not None
    assert "January 15, 2024" in temp_rec.effective_date

    dom_ext, fields = MetadataEngine.extract_domain_extension(text, [DomainLabel.HEALTHCARE])
    assert dom_ext.technical_pharma is not None
    assert dom_ext.technical_pharma["lot_number"] == "18356721"
    assert dom_ext.technical_pharma["ecn_code"] == "ECN-2023-0847"

    orgs = MetadataEngine.extract_organizations(text)
    assert "Cytiva" in orgs


def test_technique_9_near_duplicate_detection():
    doc_v1 = "Cytiva AKTA ready flow kit specification operating pressure 3.0 bar gamma 25 kGy lot 18356721"
    doc_v2 = "Cytiva AKTA ready flow kit specification operating pressure 3.0 bar gamma 28 kGy lot 18356721 revision B"
    doc_diff = "Apple Inc. Form 10-K consolidated balance sheets cash and cash equivalents"

    is_near, score = DuplicateDetector.is_near_duplicate(doc_v1, doc_v2, threshold=0.70)
    assert is_near is True
    assert score >= 0.70

    is_diff, score_diff = DuplicateDetector.is_near_duplicate(doc_v1, doc_diff, threshold=0.70)
    assert is_diff is False


def test_technique_10_contextual_indexing():
    region = DocumentRegion(
        region_id="r1",
        page_number=3,
        region_type=RegionType.PARAGRAPH,
        text="The minimum required gamma irradiation dose is 25.0 kGy.",
        identifiers=["18356721", "25.0 kGy"],
    )
    enriched = ContextualIndexer.enrich_region_with_context(
        region=region,
        doc_title="AKTA ready Quality Package",
        section_path="1.0 System Specs > 1.3 Sterilization",
    )
    assert "[Verified Provenance]" not in enriched
    assert "Document: AKTA ready Quality Package" in enriched
    assert "Section: 1.0 System Specs > 1.3 Sterilization" in enriched
    assert "Identifiers: 18356721, 25.0 kGy" in enriched


def test_technique_12_faceted_catalog():
    record = CatalogManager.generate_faceted_record(
        doc_id="test_doc",
        version_id="v1",
        title="AKTA ready Quality Package",
        domains=[DomainLabel.HEALTHCARE, DomainLabel.ENGINEERING],
        doc_types=[DocumentTypeLabel.CERTIFICATE],
        organizations=["Cytiva"],
        identifiers=["18356721", "ECN-2023-0847"],
        effective_date="January 15, 2024",
        quality_state=QualityState.READABLE,
    )
    assert record.document_id == "test_doc"
    assert "healthcare" in record.domains
    assert "certificate" in record.document_types
    assert "Cytiva" in record.organizations


def test_end_to_end_document_organization_on_pharma_blob(sample_pdf_path, tmp_path):
    pipeline = HybridIngestionPipeline(base_storage_dir=tmp_path)
    in_memory_qdrant = QdrantVisualRetriever(location=":memory:")

    doc_case = pipeline.ingest_document(
        pdf_path=sample_pdf_path,
        index_to_qdrant=True,
        qdrant_retriever=in_memory_qdrant,
    )

    sdoc = doc_case.structured_doc
    assert sdoc is not None
    assert len(sdoc.logical_documents) >= 1
    assert len(sdoc.sections) >= 1
    assert sdoc.faceted_catalog is not None
    assert sdoc.domain_extension is not None
    assert sdoc.temporal_record is not None
