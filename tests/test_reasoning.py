"""
Hermetic Unit tests for VLM Reasoning, Coordinate Grounding & Abstention Engine (Phase 4).
Uses unittest.mock to simulate hosted VLM HTTP responses, testing schema parsing,
coordinate cropping, and abstention guardrails without external network dependencies.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image

from backend.src.schemas.contracts import BoundingBox, CitationStatus, GroundedAnswer, VisualCitation
from backend.src.reasoning.grounding import GroundingEngine
from backend.src.reasoning.vlm_client import VLMClient
from backend.src.reasoning.abstention_guard import AbstentionGuard
from backend.src.ingestion.pdf_renderer import DocumentIngestionService


@pytest.fixture(scope="module")
def sample_rendered_case(tmp_path_factory) -> dict:
    base_dir = Path(__file__).resolve().parent.parent
    pdf_path = base_dir / "pharma-blob-sample.pdf"
    assert pdf_path.exists(), f"Sample PDF missing at {pdf_path}"

    temp_storage = tmp_path_factory.mktemp("reasoning_storage")
    service = DocumentIngestionService(storage_dir=temp_storage)
    doc_case = service.ingest_pdf(pdf_path, filename="pharma-blob-sample.pdf")

    crop_dir = tmp_path_factory.mktemp("crops_storage")
    grounding_engine = GroundingEngine(crop_storage_dir=crop_dir)

    return {
        "doc_case": doc_case,
        "storage_dir": temp_storage,
        "crop_dir": crop_dir,
        "grounding_engine": grounding_engine,
    }


def test_grounding_crop_evidence(sample_rendered_case: dict):
    """Test that GroundingEngine crops the requested evidence box and saves an image."""
    engine = sample_rendered_case["grounding_engine"]
    doc_case = sample_rendered_case["doc_case"]
    storage_dir = sample_rendered_case["storage_dir"]

    page_1_path = storage_dir / doc_case.doc_id / "page_1.png"
    assert page_1_path.exists()

    box = BoundingBox(ymin=380, xmin=120, ymax=440, xmax=850)
    citation = engine.crop_evidence(
        page_image_path=page_1_path,
        box=box,
        doc_id=doc_case.doc_id,
        page_number=1,
        target_type="table_cell",
    )

    assert citation.page_number == 1
    assert citation.box_2d == box
    assert citation.target_type == "table_cell"
    assert citation.source_crop_path is not None

    crop_file = sample_rendered_case["crop_dir"] / Path(citation.source_crop_path).name
    assert crop_file.exists()
    with Image.open(crop_file) as c_img:
        assert c_img.width > 0
        assert c_img.height > 0


def test_vlm_client_missing_api_key_raises_error(sample_rendered_case: dict):
    """Verify that calling VLMClient without an API key raises a clear configuration error."""
    doc_case = sample_rendered_case["doc_case"]
    page_1_path = sample_rendered_case["storage_dir"] / doc_case.doc_id / "page_1.png"

    client = VLMClient(api_key="", grounding_engine=sample_rendered_case["grounding_engine"])
    with pytest.raises(RuntimeError, match="VLM_API_KEY is not configured"):
        client.answer_page_query(
            query="Test query without key",
            page_image_path=page_1_path,
            doc_id=doc_case.doc_id,
            page_number=1,
        )


def test_vlm_client_financial_qa(sample_rendered_case: dict):
    """Test grounded financial QA parsing model response, numbers, units, and coordinates."""
    doc_case = sample_rendered_case["doc_case"]
    storage_dir = sample_rendered_case["storage_dir"]
    page_1_path = storage_dir / doc_case.doc_id / "page_1.png"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"status": "direct", "answer": "Automotive regulatory credits revenue was $554 million for Q3 2023.", "numeric_value": 554.0, "unit": "USD Millions", "bounding_box_1000": [380, 120, 440, 850], "target_type": "table_cell"}'
                }
            }
        ]
    }

    client = VLMClient(api_key="mock-key", grounding_engine=sample_rendered_case["grounding_engine"])
    with patch("httpx.Client.post", return_value=mock_response):
        answer = client.answer_page_query(
            query="What was the automotive regulatory credits revenue in Q3 2023?",
            page_image_path=page_1_path,
            doc_id=doc_case.doc_id,
            page_number=1,
        )

    assert answer.status == CitationStatus.DIRECT
    assert answer.numeric_value == 554.0
    assert answer.unit == "USD Millions"
    assert answer.citation is not None
    assert answer.citation.box_2d.ymin == 380
    assert answer.citation.box_2d.ymax == 440


def test_vlm_client_engineering_qa(sample_rendered_case: dict):
    """Test grounded engineering QA extracting pressure spec."""
    doc_case = sample_rendered_case["doc_case"]
    storage_dir = sample_rendered_case["storage_dir"]
    page_2_path = storage_dir / doc_case.doc_id / "page_2.png"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"status": "direct", "answer": "Maximum operating pressure for Hydraulic Pump Model HP-400 is 350 bar.", "numeric_value": 350.0, "unit": "bar", "bounding_box_1000": [210, 100, 290, 800], "target_type": "table_cell"}'
                }
            }
        ]
    }

    client = VLMClient(api_key="mock-key", grounding_engine=sample_rendered_case["grounding_engine"])
    with patch("httpx.Client.post", return_value=mock_response):
        answer = client.answer_page_query(
            query="What is the maximum operating pressure for Hydraulic Pump Model HP-400?",
            page_image_path=page_2_path,
            doc_id=doc_case.doc_id,
            page_number=2,
        )

    assert answer.status == CitationStatus.DIRECT
    assert answer.numeric_value == 350.0
    assert answer.unit == "bar"
    assert answer.citation.box_2d.ymin == 210


def test_vlm_client_unanswerable_abstention(sample_rendered_case: dict):
    """Test zero-hallucination abstention parsing on unanswerable query."""
    doc_case = sample_rendered_case["doc_case"]
    storage_dir = sample_rendered_case["storage_dir"]
    page_1_path = storage_dir / doc_case.doc_id / "page_1.png"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"status": "abstain", "answer": null, "numeric_value": null, "unit": null, "bounding_box_1000": null, "abstention_reason": "The queried parameter is not reported in document records."}'
                }
            }
        ]
    }

    client = VLMClient(api_key="mock-key", grounding_engine=sample_rendered_case["grounding_engine"])
    with patch("httpx.Client.post", return_value=mock_response):
        answer = client.answer_page_query(
            query="What was the battery cell manufacturing scrap rate at the Austin factory?",
            page_image_path=page_1_path,
            doc_id=doc_case.doc_id,
            page_number=1,
        )

    assert answer.status == CitationStatus.ABSTAIN
    assert answer.answer is None
    assert answer.citation is None
    assert answer.abstention_reason is not None
    assert "not reported" in answer.abstention_reason


def test_abstention_guard_enforcement():
    """Test that AbstentionGuard strictly intercepts unverified claims."""
    # 1. Answer claiming direct but missing citation box
    bad_answer = GroundedAnswer(
        query="Test query",
        status=CitationStatus.DIRECT,
        answer="A plausible sounding hallucination without proof.",
        citation=None,  # Missing citation
    )
    checked = AbstentionGuard.verify_answer(bad_answer)
    assert checked.status == CitationStatus.ABSTAIN
    assert "lacked verifiable visual" in checked.abstention_reason

    # 2. Answer with low confidence score (< 0.70)
    low_conf_answer = GroundedAnswer(
        query="Test query",
        status=CitationStatus.DIRECT,
        answer="Low confidence prediction.",
        citation=VisualCitation(
            page_number=1,
            box_2d=BoundingBox(ymin=100, xmin=100, ymax=200, xmax=200),
            confidence_score=0.45,  # Below threshold
        ),
    )
    checked_conf = AbstentionGuard.verify_answer(low_conf_answer, min_confidence=0.70)
    assert checked_conf.status == CitationStatus.ABSTAIN
    assert "below enterprise threshold" in checked_conf.abstention_reason
