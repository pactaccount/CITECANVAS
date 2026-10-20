"""
Unit tests for EvidenceDesk contracts and schemas (Phase 1 Exit Verification).
"""

import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from backend.src.schemas.contracts import (
    BoundingBox,
    CitationStatus,
    VisualCitation,
    GroundedAnswer,
    PageMetadata,
    DocumentCase,
)


def test_bounding_box_valid():
    """Test standard bounding box creation and coordinate conversion."""
    box = BoundingBox(ymin=200, xmin=100, ymax=400, xmax=600)
    assert box.ymin == 200
    assert box.xmin == 100
    assert box.ymax == 400
    assert box.xmax == 600

    # Convert to 1000x2000 pixel image
    px_xmin, px_ymin, px_xmax, px_ymax = box.to_pixel_box(image_width=1000, image_height=2000)
    assert px_xmin == 100
    assert px_ymin == 400
    assert px_xmax == 600
    assert px_ymax == 800


def test_bounding_box_invalid_inversion():
    """Test that inverted coordinates raise ValidationError."""
    with pytest.raises(ValidationError):
        BoundingBox(ymin=500, xmin=100, ymax=200, xmax=600)  # ymin > ymax

    with pytest.raises(ValidationError):
        BoundingBox(ymin=100, xmin=800, ymax=400, xmax=200)  # xmin > xmax


def test_bounding_box_out_of_bounds():
    """Test that coordinates outside 0-1000 are rejected."""
    with pytest.raises(ValidationError):
        BoundingBox(ymin=-10, xmin=0, ymax=500, xmax=500)

    with pytest.raises(ValidationError):
        BoundingBox(ymin=0, xmin=0, ymax=1050, xmax=500)


def test_bounding_box_iou():
    """Test Intersection over Union (IoU) calculation."""
    box_a = BoundingBox(ymin=100, xmin=100, ymax=300, xmax=300)
    box_b = BoundingBox(ymin=100, xmin=100, ymax=300, xmax=300)
    assert box_a.iou(box_b) == 1.0  # Identical boxes

    # Non-overlapping
    box_c = BoundingBox(ymin=400, xmin=400, ymax=600, xmax=600)
    assert box_a.iou(box_c) == 0.0

    # 50% vertical overlap, same x
    box_d = BoundingBox(ymin=200, xmin=100, ymax=400, xmax=300)
    # intersection: [200, 100, 300, 300] = 100 * 200 = 20,000
    # union = (200*200) + (200*200) - 20,000 = 60,000
    # iou = 20,000 / 60,000 = 1/3
    assert abs(box_a.iou(box_d) - (1.0 / 3.0)) < 1e-4


def test_grounded_answer_direct_valid():
    """Test valid direct citation answer."""
    answer = GroundedAnswer(
        query="What was the Q3 revenue?",
        status=CitationStatus.DIRECT,
        answer="Q3 revenue was $554 million.",
        numeric_value=554.0,
        unit="USD Millions",
        citation=VisualCitation(
            page_number=1,
            box_2d=BoundingBox(ymin=380, xmin=120, ymax=440, xmax=850),
            target_type="table_cell",
            confidence_score=0.98,
        ),
        latency_ms=120.5,
    )
    assert answer.status == CitationStatus.DIRECT
    assert answer.numeric_value == 554.0
    assert answer.citation.page_number == 1


def test_grounded_answer_abstain_requires_reason():
    """Test that abstain status requires an explicit abstention reason."""
    with pytest.raises(ValidationError):
        GroundedAnswer(
            query="What was the battery scrap rate?",
            status=CitationStatus.ABSTAIN,
            # Missing abstention_reason
        )

    # Valid abstention
    valid_abstain = GroundedAnswer(
        query="What was the battery scrap rate?",
        status=CitationStatus.ABSTAIN,
        abstention_reason="Metric is not reported in this document.",
    )
    assert valid_abstain.status == CitationStatus.ABSTAIN
    assert valid_abstain.abstention_reason is not None


def test_document_case():
    """Test DocumentCase serialization and page listing."""
    case = DocumentCase(
        doc_id="abc123sha256",
        filename="test_report.pdf",
        total_pages=2,
        uploaded_at="2026-10-16T12:00:00Z",
        pages=[
            PageMetadata(page_number=1, image_path="storage/pages/abc123sha256/page_1.png", width=2480, height=3508),
            PageMetadata(page_number=2, image_path="storage/pages/abc123sha256/page_2.png", width=2480, height=3508),
        ],
    )
    assert case.total_pages == 2
    assert len(case.pages) == 2


def test_ground_truth_fixture_loads():
    """Verify that fixtures/evaluation/ground_truth.json loads and matches schemas."""
    fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "evaluation" / "ground_truth.json"
    assert fixture_path.exists(), f"Missing fixture at {fixture_path}"

    with open(fixture_path, "r") as f:
        data = json.load(f)

    assert len(data) >= 10, f"Expected at least 10 test cases, found {len(data)}"

    for item in data:
        assert "id" in item
        assert "query" in item
        assert "expected_status" in item
        if item["expected_status"] == "direct":
            assert item["expected_page"] is not None
            box_data = item["expected_box"]
            box = BoundingBox(**box_data)
            assert box.ymin <= box.ymax
            assert box.xmin <= box.xmax
        elif item["expected_status"] == "abstain":
            assert item["expected_abstention_reason"] is not None
