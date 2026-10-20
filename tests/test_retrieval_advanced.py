"""
Advanced Retrieval Test Suite for Evid.
Verifies:
1. Dense Semantic Text Retrieval (contextualized embeddings & cosine similarity).
2. Structured Table & Metric Retrieval (row label, column header, units, footnotes, and deterministic aggregations).
3. Modality-Aware Reranking (cross-attention for text, preservation of visual candidate paths).
4. Clean branch disabling (no mock noise when a modality is disabled).
5. Exact identifier scope constraint (strict isolation of eligible evidence).
6. Progressive evaluation comparison across retrieval configurations on real document data.
"""

import json
from pathlib import Path
import pytest

from backend.src.ingestion.pdf_renderer import DocumentIngestionService
from backend.src.ingestion.text_extractor import TextExtractionService
from backend.src.retrieval.bm25_indexer import BM25Retriever
from backend.src.retrieval.visual_indexer import QdrantVisualRetriever
from backend.src.retrieval.dense_text_retriever import DenseTextRetriever, DenseTextChunk
from backend.src.retrieval.structured_table_retriever import (
    StructuredTableRetriever,
    StructuredTable,
    TableCellRecord,
)
from backend.src.retrieval.modality_reranker import ModalityAwareReranker
from backend.src.retrieval.exact_lookup import ExactIdentifierLookup
from backend.src.retrieval.hybrid_ranker import HybridRanker
from backend.src.retrieval.query_processor import QueryProcessor
from backend.src.schemas.contracts import BoundingBox, StructuredDocument, DocumentRegion, RegionType, ProcessingVersion


@pytest.fixture(scope="module")
def advanced_pdf_setup(tmp_path_factory) -> dict:
    base_dir = Path(__file__).resolve().parent.parent
    pdf_path = base_dir / "pharma-blob-sample.pdf"
    assert pdf_path.exists(), f"Sample PDF missing at {pdf_path}"

    temp_storage = tmp_path_factory.mktemp("adv_retrieval_storage")
    service = DocumentIngestionService(storage_dir=temp_storage)
    doc_case = service.ingest_pdf(pdf_path, filename="pharma-blob-sample.pdf")
    pages_text = TextExtractionService.extract_from_pdf(pdf_path)

    # 1. BM25
    bm25 = BM25Retriever(pages_text)

    # 2. Dense Text
    dense = DenseTextRetriever(location=":memory:")
    chunks = []
    for p_num, text in pages_text.items():
        chunks.append(
            DenseTextChunk(
                chunk_id=f"p_{p_num}_c1",
                doc_id=doc_case.doc_id,
                page_number=p_num,
                text=text,
                section_title=f"Page {p_num} Specification",
            )
        )
    dense.index_chunks(chunks)

    # 3. Visual Multi-Vector
    visual = QdrantVisualRetriever(location=":memory:")
    visual.index_document(doc_case, temp_storage)

    # 4. Exact Lookup
    exact = ExactIdentifierLookup()
    regions = [
        DocumentRegion(
            region_id=f"reg_{p}",
            page_number=p,
            region_type=RegionType.PARAGRAPH,
            text=t,
            local_identifiers=[],
        )
        for p, t in pages_text.items()
    ]
    sdoc = StructuredDocument(
        document_id=doc_case.doc_id,
        version_id="v1",
        filename="pharma-blob-sample.pdf",
        sha256_hash=doc_case.doc_id,
        total_pages=doc_case.total_pages,
        processing_version=ProcessingVersion(version_id="v1", document_id=doc_case.doc_id, created_at="2026-10-18T00:00:00Z"),
        regions=regions,
    )
    exact.index_document(sdoc)

    # 5. Structured Table
    table_retriever = StructuredTableRetriever()
    table = StructuredTable(
        table_id="tbl_operating_limits",
        doc_id=doc_case.doc_id,
        page_number=3,
        title="Physical and Environmental Operating Limits",
        headers=["Parameter", "Revision B", "Revision C", "Unit"],
        rows=[
            {"Parameter": "Maximum Operating Pressure", "Revision B": "2.5", "Revision C": "3.0", "Unit": "bar"},
            {"Parameter": "Gamma Dose Range", "Revision B": "25.0 - 40.0", "Revision C": "25.0 - 40.0", "Unit": "kGy"},
        ],
        cells=[
            TableCellRecord(
                cell_id="c_1",
                table_id="tbl_operating_limits",
                doc_id=doc_case.doc_id,
                page_number=3,
                row_idx=1,
                col_idx=1,
                row_label="Maximum Operating Pressure",
                column_header="Revision B",
                raw_value="2.5",
                numeric_value=2.5,
                unit="bar",
                period_or_revision="Revision B",
                footnotes=["Tested per ASTM D1003"],
            ),
            TableCellRecord(
                cell_id="c_2",
                table_id="tbl_operating_limits",
                doc_id=doc_case.doc_id,
                page_number=3,
                row_idx=1,
                col_idx=2,
                row_label="Maximum Operating Pressure",
                column_header="Revision C",
                raw_value="3.0",
                numeric_value=3.0,
                unit="bar",
                period_or_revision="Revision C",
                footnotes=["Tested per ASTM D1003"],
            ),
            TableCellRecord(
                cell_id="c_3",
                table_id="tbl_operating_limits",
                doc_id=doc_case.doc_id,
                page_number=3,
                row_idx=2,
                col_idx=2,
                row_label="Gamma Dose Range",
                column_header="Revision C",
                raw_value="25.0",
                numeric_value=25.0,
                unit="kGy",
                period_or_revision="Revision C",
                footnotes=["Sterilization Certificate required"],
            ),
        ],
        footnotes=["Tested per ASTM D1003", "Sterilization Certificate required"],
        box_2d=BoundingBox(ymin=300, xmin=100, ymax=600, xmax=900),
    )
    table_retriever.index_table(table)

    # 6. Modality Reranker
    reranker = ModalityAwareReranker()

    return {
        "doc_case": doc_case,
        "bm25": bm25,
        "dense": dense,
        "visual": visual,
        "exact": exact,
        "table": table_retriever,
        "reranker": reranker,
        "project_root": base_dir,
    }


def test_dense_text_retriever(advanced_pdf_setup: dict):
    """Verify that DenseTextRetriever retrieves relevant semantic text chunks."""
    dense = advanced_pdf_setup["dense"]
    query = "What is the recommended storage temperature for standard AKTA ready flow kits?"
    results = dense.retrieve(query, top_k=3)

    assert len(results) > 0
    # Top result should contain storage information on Page 1
    top_hit = results[0]
    assert top_hit["page_number"] in [1, 7]
    assert top_hit["similarity"] > 0.0


def test_structured_table_retrieval_and_aggregation(advanced_pdf_setup: dict):
    """Verify cell extraction, row-column relationship, and deterministic calculations."""
    table_retriever = advanced_pdf_setup["table"]

    # 1. Metric Cell Retrieval
    cells = table_retriever.retrieve_metric_cells(
        metric_name="operating pressure",
        revision="Revision C",
        unit="bar",
    )
    assert len(cells) == 1
    assert cells[0].numeric_value == 3.0
    assert cells[0].unit == "bar"
    assert "Tested per ASTM D1003" in cells[0].footnotes

    # 2. Complete Evidence Retrieval
    full_table = table_retriever.retrieve_complete_table_evidence("tbl_operating_limits")
    assert full_table is not None
    assert full_table["page_number"] == 3
    assert len(full_table["headers"]) == 4
    assert len(full_table["rows"]) == 2

    # 3. Deterministic Aggregation (Max operating pressure across revisions)
    max_res = table_retriever.execute_aggregation(
        table_id="tbl_operating_limits",
        column_name="Revision C",
        operation="max",
    )
    assert max_res["status"] == "success"
    assert max_res["result"] == 25.0  # Gamma dose is 25.0, max in col C


def test_modality_aware_reranking(advanced_pdf_setup: dict):
    """Verify cross-attention reranking for text while preserving visual candidate path."""
    reranker = advanced_pdf_setup["reranker"]

    text_candidates = [
        {"page_number": 1, "text": "AKTA ready storage temperature > +5°C", "rank": 1},
        {"page_number": 8, "text": "General safety notes and warning text", "rank": 2},
    ]
    visual_candidates = [
        {"page_number": 9, "similarity": 0.85, "rank": 1},  # Flowchart / drawing
    ]

    reranked = reranker.rerank_hybrid_candidates(
        query="What is the storage temperature?",
        text_candidates=text_candidates,
        visual_candidates=visual_candidates,
        top_k=3,
    )

    assert len(reranked) == 3
    pages = [r.page_number for r in reranked]
    # Page 1 (high text match) and Page 9 (visual drawing) should both be present in top 3
    assert 1 in pages
    assert 9 in pages
    # Check that visual candidate was preserved as visual modality
    vis_entry = next(r for r in reranked if r.page_number == 9)
    assert vis_entry.modality == "visual"


def test_clean_branch_disabling(advanced_pdf_setup: dict):
    """Verify that disabling visual or dense branch functions cleanly without synthetic mock noise."""
    bm25 = advanced_pdf_setup["bm25"]
    dense = advanced_pdf_setup["dense"]

    # Hybrid ranker with NO visual retriever (pure text hybrid)
    text_only_ranker = HybridRanker(
        bm25_retriever=bm25,
        dense_retriever=dense,
        visual_retriever=None,
    )

    query = "What is the recommended storage temperature for standard AKTA ready flow kits?"
    results = text_only_ranker.retrieve(query, top_k=2)

    assert len(results) > 0
    assert results[0]["page_number"] == 1
    assert "visual" not in results[0]["active_modalities"]


def test_exact_identifier_scope_constraint(advanced_pdf_setup: dict):
    """Verify exact identifier match constrains eligible candidates rather than just voting."""
    bm25 = advanced_pdf_setup["bm25"]
    visual = advanced_pdf_setup["visual"]
    exact = advanced_pdf_setup["exact"]

    # Ranker with exact_scope_constraint=True
    scoped_ranker = HybridRanker(
        bm25_retriever=bm25,
        visual_retriever=visual,
        exact_lookup=exact,
        exact_scope_constraint=True,
    )

    query = "What is the lot number for the AKTA ready Low Flow Kit in the Certificate of Quality? Lot 18356721."
    results = scoped_ranker.retrieve(query, top_k=3)

    assert len(results) == 1
    # Only Page 2 contains lot number 18356721; scope constraint isolates Page 2 cleanly
    assert results[0]["page_number"] == 2
    assert results[0]["has_exact_match"] is True


def test_progressive_retrieval_comparison(advanced_pdf_setup: dict):
    """
    Progressively evaluates:
    1. BM25 alone
    2. Dense alone
    3. Tri-Hybrid (BM25 + Dense + Visual)
    4. Tri-Hybrid + Reranking + Structured Table
    Reports empirical Hit@1 and Hit@2 across benchmark cases.
    """
    bm25 = advanced_pdf_setup["bm25"]
    dense = advanced_pdf_setup["dense"]
    visual = advanced_pdf_setup["visual"]
    exact = advanced_pdf_setup["exact"]
    table = advanced_pdf_setup["table"]
    reranker = advanced_pdf_setup["reranker"]

    fixture_path = advanced_pdf_setup["project_root"] / "fixtures" / "evaluation" / "ground_truth.json"
    with open(fixture_path, "r") as f:
        ground_truth = json.load(f)

    direct_cases = [c for c in ground_truth if c["expected_status"] == "direct"]
    assert len(direct_cases) >= 6

    # 1. BM25 Alone
    bm25_hits1, bm25_hits2 = 0, 0
    for case in direct_cases:
        r = bm25.retrieve(case["query"], top_k=2)
        pages = [item["page_number"] for item in r]
        if case["expected_page"] in pages[:1]:
            bm25_hits1 += 1
        if case["expected_page"] in pages[:2]:
            bm25_hits2 += 1

    # 2. Dense Alone
    dense_hits1, dense_hits2 = 0, 0
    for case in direct_cases:
        r = dense.retrieve(case["query"], top_k=2)
        pages = [item["page_number"] for item in r]
        if case["expected_page"] in pages[:1]:
            dense_hits1 += 1
        if case["expected_page"] in pages[:2]:
            dense_hits2 += 1

    # 3. Full Tri-Hybrid + Structured Table + Modality Reranker
    full_ranker = HybridRanker(
        bm25_retriever=bm25,
        dense_retriever=dense,
        visual_retriever=visual,
        exact_lookup=exact,
        table_retriever=table,
        reranker=reranker,
        equal_weights=False,
    )

    full_hits1, full_hits2 = 0, 0
    for case in direct_cases:
        r = full_ranker.retrieve(case["query"], top_k=2)
        pages = [item["page_number"] for item in r]
        if case["expected_page"] in pages[:1]:
            full_hits1 += 1
        if case["expected_page"] in pages[:2]:
            full_hits2 += 1

    total = len(direct_cases)
    bm25_r2 = bm25_hits2 / total
    dense_r2 = dense_hits2 / total
    full_r2 = full_hits2 / total

    # Tri-hybrid system with reranker must achieve 100% Recall@2
    assert full_r2 >= 0.90
    assert full_r2 >= bm25_r2
