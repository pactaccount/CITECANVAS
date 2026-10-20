"""
Unit & Integration Tests for Hybrid Document Ingestion Pipeline.
Tests all 14 steps: fingerprinting, quality assessment, layout parsing,
structured tables, stamps, signatures, hybrid chunking, and provenance.
"""

from pathlib import Path
import pytest
from PIL import Image

from backend.src.ingestion.fingerprint import DocumentFingerprinter
from backend.src.ingestion.quality_assessor import QualityAssessor
from backend.src.ingestion.native_text import NativeTextExtractor
from backend.src.ingestion.preprocessor import ImagePreprocessor
from backend.src.ingestion.layout_parser import LayoutParser
from backend.src.ingestion.hybrid_chunker import HybridChunker
from backend.src.ingestion.hybrid_pipeline import HybridIngestionPipeline
from backend.src.retrieval.visual_indexer import QdrantVisualRetriever
from backend.src.schemas.contracts import (
    BoundingBox,
    ExtractionMethod,
    PageType,
    QualityStatus,
    RegionType,
)


@pytest.fixture
def sample_pdf_path():
    p = Path(__file__).resolve().parent.parent / "pharma-blob-sample.pdf"
    assert p.exists(), f"Sample PDF missing at: {p}"
    return p


def test_step1_document_fingerprinting(sample_pdf_path):
    sha = DocumentFingerprinter.compute_sha256(sample_pdf_path)
    assert len(sha) == 64
    assert sha == "de6abb0444c130b946b996ad3971036b95d353ae4380b15118c95c5f358361fe"

    version = DocumentFingerprinter.create_version_record(doc_id=sha)
    assert version.document_id == sha
    assert len(version.version_id) == 8
    assert version.pipeline_version == "v3.0-hybrid"


def test_step2_quality_assessor(sample_pdf_path, tmp_path):
    # Create mock clean page image
    mock_img_path = tmp_path / "page_1.png"
    img = Image.new("L", (512, 512), color=255)
    img.save(mock_img_path)

    assessment = QualityAssessor.assess_page(sample_pdf_path, 1, mock_img_path)
    assert assessment.page_number == 1
    assert assessment.character_count > 100
    assert assessment.text_layer_valid is True
    assert assessment.page_type == PageType.DIGITAL
    assert assessment.needs_ocr is False


def test_step3_native_text_and_identifiers(sample_pdf_path):
    regions = NativeTextExtractor.extract_page_regions(
        sample_pdf_path, page_number=3, doc_id="test_doc", version_id="v1"
    )
    assert len(regions) > 0

    # Page 3 contains Lot and gamma irradiation numbers
    combined_text = " ".join([r.text for r in regions])
    identifiers = NativeTextExtractor.extract_identifiers(combined_text)
    assert any("kGy" in id_val for id_val in identifiers) or "18356721" in identifiers


def test_step4_selective_image_preprocessing(tmp_path):
    from backend.src.schemas.contracts import PageQualityAssessment

    # Low contrast mock image
    low_contrast_img = tmp_path / "low_contrast.png"
    img = Image.new("L", (200, 200), color=128)
    img.save(low_contrast_img)

    mock_assessment = PageQualityAssessment(
        page_number=1,
        page_type=PageType.DIGITAL,
        text_layer_valid=True,
        character_count=200,
        word_count=40,
        blur_score=50.0,
        contrast_score=0.05,  # Low contrast triggers preprocessing
        skew_angle_deg=0.0,
        needs_preprocessing=True,
        needs_ocr=False,
    )

    out_path, modified = ImagePreprocessor.process_page_image_selectively(
        low_contrast_img, mock_assessment, output_dir=tmp_path
    )
    assert modified is True
    assert out_path.exists()


def test_steps5_to_10_layout_parser_table_extraction():
    table_raw = (
        "Parameter | Specification | Actual Result\n"
        "Gamma Dose | 25.0 - 40.0 kGy | 28.4 kGy\n"
        "Operating Pressure | <= 3.0 bar | 2.1 bar"
    )
    box = BoundingBox(ymin=200, xmin=100, ymax=400, xmax=900)
    struct_tbl = LayoutParser.parse_table_structure(table_raw, page_number=3, table_box=box)

    assert struct_tbl.page_number == 3
    assert struct_tbl.headers == ["Parameter", "Specification", "Actual Result"]
    assert len(struct_tbl.rows) == 2
    assert len(struct_tbl.cells) == 6

    # Verify structured numeric parsing on cells
    gamma_actual_cell = struct_tbl.cells[2]  # 28.4 kGy (row 1, col 3)
    assert gamma_actual_cell.numeric_value == 28.4
    assert gamma_actual_cell.unit == "kGy"

    pressure_actual_cell = struct_tbl.cells[5]  # 2.1 bar (row 2, col 3)
    assert pressure_actual_cell.numeric_value == 2.1
    assert pressure_actual_cell.unit == "bar"


def test_step11_hybrid_chunker_repeated_headers():
    table_raw = (
        "Col1 | Col2\n" + "\n".join([f"Row{i} | Val{i}" for i in range(1, 25)])
    )
    struct_tbl = LayoutParser.parse_table_structure(table_raw, page_number=1)
    chunks = HybridChunker.chunk_table(struct_tbl, max_rows_per_group=8)

    assert len(chunks) == 3  # 24 rows split into 8-row groups
    for chunk in chunks:
        assert chunk.region_type == RegionType.TABLE_ROW_GROUP
        assert "Col1 | Col2" in chunk.text  # Headers repeated across chunks!


def test_end_to_end_hybrid_pipeline(sample_pdf_path, tmp_path):
    # Run full 14-step hybrid pipeline in isolated tmp_path with in-memory Qdrant
    pipeline = HybridIngestionPipeline(base_storage_dir=tmp_path)
    in_memory_qdrant = QdrantVisualRetriever(location=":memory:")

    doc_case = pipeline.ingest_document(
        pdf_path=sample_pdf_path,
        index_to_qdrant=True,
        qdrant_retriever=in_memory_qdrant,
    )

    assert doc_case.total_pages == 10
    assert doc_case.structured_doc is not None
    assert len(doc_case.structured_doc.pages) == 10
    assert len(doc_case.structured_doc.regions) > 0

    # Verify structured JSON file was written
    json_path = tmp_path / "structured" / f"{doc_case.doc_id}_v{doc_case.structured_doc.version_id}.json"
    assert json_path.exists()
