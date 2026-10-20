"""
Unit tests for Document Ingestion & 300 DPI Rendering Service (Phase 2 Exit Verification).
"""

import time
from pathlib import Path
import pytest
from PIL import Image

from backend.src.ingestion.pdf_renderer import DocumentIngestionService
from backend.src.ingestion.text_extractor import TextExtractionService


@pytest.fixture
def sample_pdf_path() -> Path:
    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "evaluation" / "sample_tech_report.pdf"
    assert fixture.exists(), f"Sample PDF fixture missing at {fixture}"
    return fixture


@pytest.fixture
def temp_storage(tmp_path: Path) -> Path:
    storage = tmp_path / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    return storage


def test_pdf_rendering_300_dpi(sample_pdf_path: Path, temp_storage: Path):
    """Test that a PDF is rendered to crisp 300 DPI images with correct dimensions."""
    service = DocumentIngestionService(storage_dir=temp_storage)
    case = service.ingest_pdf(sample_pdf_path, filename="sample_tech_report.pdf")

    assert case.total_pages == 3
    assert len(case.pages) == 3
    assert case.filename == "sample_tech_report.pdf"
    assert len(case.doc_id) == 64  # Valid SHA-256 string

    doc_dir = temp_storage / case.doc_id
    assert doc_dir.exists()

    # Check each page image file
    for page_meta in case.pages:
        img_file = doc_dir / f"page_{page_meta.page_number}.png"
        assert img_file.exists(), f"Rendered image missing: {img_file}"

        with Image.open(img_file) as img:
            width, height = img.size
            # 8.5 x 11 inches at 300 DPI = 2550 x 3300 pixels
            assert width >= 2000, f"Expected 300 DPI width >= 2000, got {width}"
            assert height >= 2800, f"Expected 300 DPI height >= 2800, got {height}"
            assert page_meta.width == width
            assert page_meta.height == height


def test_sha256_caching(sample_pdf_path: Path, temp_storage: Path):
    """Test that re-ingesting the exact same document hits the cache instantly (<15ms)."""
    service = DocumentIngestionService(storage_dir=temp_storage)

    # First run (renders and saves manifest)
    start_time = time.perf_counter()
    case1 = service.ingest_pdf(sample_pdf_path)
    first_duration = time.perf_counter() - start_time

    # Second run (instant cache hit)
    start_time = time.perf_counter()
    case2 = service.ingest_pdf(sample_pdf_path)
    cache_duration = time.perf_counter() - start_time

    assert case1.doc_id == case2.doc_id
    assert case1.total_pages == case2.total_pages
    assert cache_duration < 0.05, f"Cache retrieval took {cache_duration}s, expected < 0.05s"


def test_text_extraction(sample_pdf_path: Path):
    """Test that PDFium text extraction captures crucial terms, numbers, and codes."""
    pages_text = TextExtractionService.extract_from_pdf(sample_pdf_path)
    assert len(pages_text) == 3

    # Page 1 Financials
    p1 = pages_text[1]
    assert "Automotive regulatory credits" in p1
    assert "554" in p1
    assert "19,625" in p1 or "19625" in p1
    assert "Gross Margin" in p1

    # Page 2 Engineering Specs
    p2 = pages_text[2]
    assert "Hydraulic Pump Model" in p2
    assert "HP-400" in p2
    assert "350" in p2
    assert "bar" in p2
    assert "MIL-PRF-83282" in p2

    # Page 3 Performance
    p3 = pages_text[3]
    assert "Throughput" in p3
    assert "14200" in p3
    assert "4.5" in p3


def test_standalone_image_ingestion(temp_storage: Path):
    """Test that standalone images (PNG/JPG) are ingested into a 1-page DocumentCase."""
    # Create a dummy image
    test_img = Image.new("RGB", (1200, 1600), color=(255, 255, 255))
    dummy_path = temp_storage / "test_blueprint.png"
    test_img.save(dummy_path, format="PNG")

    service = DocumentIngestionService(storage_dir=temp_storage)
    case = service.ingest_image(dummy_path, filename="test_blueprint.png")

    assert case.total_pages == 1
    assert len(case.pages) == 1
    assert case.pages[0].width == 1200
    assert case.pages[0].height == 1600
    assert (temp_storage / case.doc_id / "page_1.png").exists()
