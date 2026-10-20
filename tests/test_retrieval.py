"""
Unit tests for Hybrid Retrieval Engine (Phase 3 Exit Verification).
Tests BM25 lexical search, Qdrant visual embeddings, and Reciprocal Rank Fusion (RRF).
"""

import json
from pathlib import Path
import pytest

from backend.src.ingestion.pdf_renderer import DocumentIngestionService
from backend.src.ingestion.text_extractor import TextExtractionService
from backend.src.retrieval.bm25_indexer import BM25Retriever
from backend.src.retrieval.visual_indexer import QdrantVisualRetriever
from backend.src.retrieval.hybrid_ranker import HybridRanker


@pytest.fixture(scope="module")
def sample_pdf_data(tmp_path_factory) -> dict:
    base_dir = Path(__file__).resolve().parent.parent
    pdf_path = base_dir / "pharma-blob-sample.pdf"
    assert pdf_path.exists(), f"Sample PDF missing at {pdf_path}"

    temp_storage = tmp_path_factory.mktemp("retrieval_storage")
    service = DocumentIngestionService(storage_dir=temp_storage)
    doc_case = service.ingest_pdf(pdf_path, filename="pharma-blob-sample.pdf")
    pages_text = TextExtractionService.extract_from_pdf(pdf_path)

    return {
        "doc_case": doc_case,
        "pages_text": pages_text,
        "storage_dir": temp_storage,
        "project_root": base_dir,
    }


def test_bm25_retrieval_exact_codes(sample_pdf_data: dict):
    """Test that BM25 retrieves exact pages for specific alphanumeric codes and terms."""
    bm25 = BM25Retriever(sample_pdf_data["pages_text"])

    # Query 1: Storage temperature on Page 1
    r1 = bm25.retrieve("What is the recommended storage temperature for standard AKTA ready flow kits?", top_k=1)
    assert len(r1) > 0
    assert r1[0]["page_number"] == 1

    # Query 2: Lot number on Page 2
    r2 = bm25.retrieve("What is the lot number for the AKTA ready Low Flow Kit in the Certificate of Quality?", top_k=1)
    assert len(r2) > 0
    assert r2[0]["page_number"] == 2

    # Query 3: ECN Number on Page 5
    r3 = bm25.retrieve("What was the ECN number for revision C in the Configuration Change History?", top_k=1)
    assert len(r3) > 0
    assert r3[0]["page_number"] == 5


def test_qdrant_visual_retrieval(sample_pdf_data: dict):
    """Test that Qdrant indexes pages and retrieves candidates based on visual queries."""
    retriever = QdrantVisualRetriever(location=":memory:")
    retriever.index_document(sample_pdf_data["doc_case"], sample_pdf_data["storage_dir"])

    res = retriever.retrieve("Show the packaging component layout and drawing reference", top_k=2)
    assert len(res) > 0
    assert all(1 <= item["page_number"] <= sample_pdf_data["doc_case"].total_pages for item in res)


def test_hybrid_rrf_golden_recall(sample_pdf_data: dict):
    """
    Test that Hybrid Ranker (RRF) achieves high Recall@2 on the golden evaluation dataset.
    """
    bm25 = BM25Retriever(sample_pdf_data["pages_text"])
    visual = QdrantVisualRetriever(location=":memory:")
    visual.index_document(sample_pdf_data["doc_case"], sample_pdf_data["storage_dir"])

    ranker = HybridRanker(bm25_retriever=bm25, visual_retriever=visual)

    fixture_path = sample_pdf_data["project_root"] / "fixtures" / "evaluation" / "ground_truth.json"
    with open(fixture_path, "r") as f:
        ground_truth = json.load(f)

    # Filter to answerable questions (direct citations)
    direct_cases = [c for c in ground_truth if c["expected_status"] == "direct"]
    assert len(direct_cases) >= 6

    hits_at_1 = 0
    hits_at_2 = 0

    for case in direct_cases:
        query = case["query"]
        expected_page = case["expected_page"]

        top_candidates = ranker.retrieve(query, top_k=2)
        candidate_pages = [c["page_number"] for c in top_candidates]

        if expected_page in candidate_pages[:1]:
            hits_at_1 += 1
        if expected_page in candidate_pages[:2]:
            hits_at_2 += 1

    recall_at_1 = hits_at_1 / len(direct_cases)
    recall_at_2 = hits_at_2 / len(direct_cases)

    # Assert Recall@2 meets enterprise quality gate (> 90%)
    assert recall_at_2 >= 0.90, f"Recall@2 was {recall_at_2:.2%}, expected >= 90%"
    assert recall_at_1 >= 0.75, f"Recall@1 was {recall_at_1:.2%}, expected >= 75%"
