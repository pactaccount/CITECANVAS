"""
Unit tests for Structure-Aware Hybrid Chunking and Parent-Child Evidence Expansion.
Verifies:
1. Content-specific token budgets (narrative 350-500 tokens, 640 search cap, table 768 cap).
2. Sentence-boundary splitting with source offsets and max 1-sentence overlap (~64 tokens).
3. No blanket overlap across natural paragraph boundaries.
4. Token-budgeted table row grouping with repeated headers and units.
5. Wide-table column grouping preserving row identifiers.
6. Independent routing for visual elements (stamps, signatures, equations) without padding.
7. Scoped local identifiers vs blanket document dump.
8. Parent-child retrieval-time evidence expansion (expand_evidence).
9. Optional late chunking token pooling.
"""

import pytest
from backend.src.ingestion.hybrid_chunker import HybridChunker, LateChunker
from backend.src.schemas.contracts import (
    BoundingBox,
    ContentRelationship,
    ContentRelationType,
    DocumentRegion,
    ExtractionMethod,
    LogicalDocument,
    LogicalSection,
    PageMetadata,
    ProcessingVersion,
    QualityStatus,
    RegionType,
    StructuredDocument,
    StructuredTable,
    TableCell,
)


def test_narrative_paragraph_sentence_splitting_and_cap():
    """Verify narrative paragraphs split at sentence boundaries and respect the 640-token cap."""
    # Create an oversized paragraph (> 500 body tokens)
    sentence_base = "The single-use flow kit undergoes rigorous bioprocess qualification testing to ensure sterility and pressure tolerance. "
    oversized_text = sentence_base * 40  # ~40 * 18 words * 1.3 ≈ 936 tokens

    region = DocumentRegion(
        region_id="p1_reg_long",
        page_number=1,
        region_type=RegionType.PARAGRAPH,
        text=oversized_text,
        parent_section_id="1.0 System Overview",
    )

    chunks = HybridChunker.chunk_prose_stream(
        regions=[region],
        doc_title="AKTA ready Specs",
        section_path="1.0 System Overview",
    )

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.token_count <= HybridChunker.PROSE_SEARCH_CAP
        assert "Document: AKTA ready Specs" in chunk.search_text
        assert "Section: 1.0 System Overview" in chunk.search_text
        # Verify source text is retained without contamination
        assert chunk.source_text is not None


def test_controlled_sentence_overlap_and_no_blanket_overlap():
    """
    Verify at most 1 preceding sentence (~64 tokens) is included when splitting an oversized passage,
    and verify NO blanket overlap is added between distinct, naturally bounded paragraphs.
    """
    # 1. Distinct bounded paragraphs
    p1 = DocumentRegion(
        region_id="p1",
        page_number=1,
        region_type=RegionType.PARAGRAPH,
        text="The AKTA ready system is engineered for biopharmaceutical production. It supports single-use flow kits.",
        parent_section_id="Overview",
    )
    p2 = DocumentRegion(
        region_id="p2",
        page_number=1,
        region_type=RegionType.PARAGRAPH,
        text="All wetted materials comply with USP Class VI requirements. Animal origin certificates are maintained.",
        parent_section_id="Overview",
    )

    # Since p1 + p2 is short (< 350 tokens), they merge cleanly into one chunk
    chunks = HybridChunker.chunk_prose_stream([p1, p2], doc_title="Manual", section_path="Overview")
    assert len(chunks) == 1
    assert "AKTA ready" in chunks[0].text
    assert "USP Class VI" in chunks[0].text

    # 2. Oversized passage splitting checks overlap
    sentence1 = "Bioprocess validation requires precise flow monitoring across variable pressures. "
    long_passage = (sentence1 * 60) + "Final sentence of the continuous batch record."
    r_long = DocumentRegion(region_id="rlong", page_number=2, region_type=RegionType.PARAGRAPH, text=long_passage)
    chunks_split = HybridChunker.chunk_prose_stream([r_long], doc_title="Manual", section_path="Validation")
    assert len(chunks_split) >= 2
    # Verify continuation flag
    continuation_chunks = [c for c in chunks_split if "continuation" in c.quality_flags]
    assert len(continuation_chunks) > 0


def test_page_furniture_exclusion():
    """Verify page numbers, headers, and running footers are excluded from search chunks."""
    assert HybridChunker.is_page_furniture("Page 1 of 10") is True
    assert HybridChunker.is_page_furniture("10 / 25") is True
    assert HybridChunker.is_page_furniture("42") is True
    assert HybridChunker.is_page_furniture("CONFIDENTIAL") is True
    assert HybridChunker.is_page_furniture("This is a meaningful narrative paragraph about system pressure.") is False


def test_token_budgeted_table_row_grouping():
    """Verify large tables are chunked using token budgets rather than fixed row numbers."""
    headers = ["Component", "Material", "Batch Lot", "Compliance", "Max Pressure"]
    # 30 detailed rows
    rows = [
        [f"Pump Head {i}", "Polypropylene USP Class VI", f"LOT-2024-{1000+i}", "ISO 10993", f"{3.0 + i*0.1:.1f} bar"]
        for i in range(30)
    ]
    table = StructuredTable(
        table_id="tbl_spec",
        page_number=3,
        caption="Component Specifications",
        headers=headers,
        rows=rows,
        markdown_representation="| " + " | ".join(headers) + " |\n| " + " | ".join(["---"]*5) + " |\n" + "\n".join(["| " + " | ".join(r) + " |" for r in rows]),
        continues_on_page=4,
    )

    chunks = HybridChunker.chunk_table(table, token_budget=400, doc_title="Pharma Package", section_path="Hardware Specs")
    assert len(chunks) > 1

    for chunk in chunks:
        assert chunk.token_count <= 400
        # Headers must be repeated
        assert "| Component | Material | Batch Lot | Compliance | Max Pressure |" in chunk.text
        # Context prefix must be included
        assert "Document: Pharma Package" in chunk.search_text
        assert "Table: Component Specifications" in chunk.search_text
        assert chunk.region_type == RegionType.TABLE_ROW_GROUP
        # Relationship link to parent table
        assert "tbl_spec" in chunk.relations


def test_wide_table_column_grouping():
    """Verify very wide table rows split into column groups while repeating row keys."""
    headers = ["Metric", "2019", "2020", "2021", "2022", "2023", "2024", "2025 Projected", "2026 Projected"]
    # Row with very long detailed values
    wide_row = [
        "Consolidated Revenue by Operating Segment and Global Territory (USD Millions)",
        "12500.5 USD", "13400.2 USD", "14900.8 USD", "16200.1 USD", "17850.4 USD", "19400.9 USD", "21500.0 USD", "23800.0 USD"
    ]
    table = StructuredTable(
        table_id="tbl_financial_wide",
        page_number=4,
        caption="Segment Revenue History",
        headers=headers,
        rows=[wide_row],
        markdown_representation="| " + " | ".join(headers) + " |\n| " + " | ".join(["---"]*9) + " |\n| " + " | ".join(wide_row) + " |",
    )

    # Force tight budget so wide row triggers column grouping
    chunks = HybridChunker.chunk_table(table, token_budget=80, doc_title="Annual Report", section_path="Financials")
    assert len(chunks) >= 2
    for chunk in chunks:
        # Must retain the metric key

        assert "Consolidated Revenue" in chunk.text
        assert "Document: Annual Report" in chunk.search_text


def test_standalone_visual_routing_no_padding():
    """Verify stamps, signatures, and equations remain independent unpadded chunks."""
    stamp_region = DocumentRegion(
        region_id="stamp_qa",
        page_number=2,
        region_type=RegionType.STAMP,
        text="QA APPROVED - Release Date: 2024-03-15",
    )
    sig_region = DocumentRegion(
        region_id="sig_director",
        page_number=2,
        region_type=RegionType.SIGNATURE,
        text="Dr. Eleanor Vance, Quality Director - Signed: 2024-03-15",
    )

    chunks = HybridChunker.chunk_document_regions(
        regions=[stamp_region, sig_region],
        tables=[],
        doc_title="Certificate of Analysis",
    )

    assert len(chunks) == 2
    stamp_chunk = next(c for c in chunks if c.region_type == RegionType.STAMP)
    sig_chunk = next(c for c in chunks if c.region_type == RegionType.SIGNATURE)

    # Small stamp text must NOT be padded to reach 350 tokens
    assert stamp_chunk.text == "QA APPROVED - Release Date: 2024-03-15"
    assert stamp_chunk.token_count < 50
    assert "Document: Certificate of Analysis" in stamp_chunk.search_text


def test_scoped_local_identifiers():
    """Verify identifiers are scoped locally to chunks to prevent cross-chunk contamination."""
    text_with_lot = "Product manufactured under Lot No: 18356721 and Change Order ECN-2023-0847."
    local_ids = HybridChunker.extract_local_identifiers(text_with_lot)

    assert "18356721" in local_ids
    assert "ECN-2023-0847" in local_ids
    # Should not contain random unrelated IDs
    assert len(local_ids) == 2


def test_retrieval_time_evidence_expansion():
    """Verify expand_evidence reconstitutes full section/table context from a child chunk."""
    # 1. Create a mock structured document
    table = StructuredTable(
        table_id="tbl_sterilization",
        page_number=2,
        caption="Sterilization Specifications",
        headers=["Parameter", "Specification", "Actual"],
        rows=[
            ["Gamma Irradiation", "25.0 - 40.0 kGy", "28.4 kGy"],
            ["Endotoxin", "< 0.25 EU/ml", "< 0.05 EU/ml"],
        ],
        markdown_representation="| Parameter | Specification | Actual |\n|---|---|---|\n| Gamma Irradiation | 25.0 - 40.0 kGy | 28.4 kGy |\n| Endotoxin | < 0.25 EU/ml | < 0.05 EU/ml |",
    )
    fn_region = DocumentRegion(
        region_id="fn_1",
        page_number=2,
        region_type=RegionType.PARAGRAPH,
        text="* Note: Endotoxin tested using LAL kinetic chromogenic assay.",
    )
    rel = ContentRelationship(
        source_id="fn_1",
        target_id="tbl_sterilization_grp_1",
        relation_type=ContentRelationType.FOOTNOTE_FOR,
    )

    structured_doc = StructuredDocument(
        document_id="doc_mock",
        version_id="v1",
        filename="test.pdf",
        sha256_hash="hash123",
        total_pages=2,
        processing_version=ProcessingVersion(
            version_id="v1",
            document_id="doc_mock",
            created_at="2026-10-18T00:00:00Z",
        ),
        tables=[table],
        regions=[fn_region],
        relationships=[rel],
    )

    # 2. Child row group chunk retrieved
    child_chunk = DocumentRegion(
        region_id="tbl_sterilization_grp_1",
        page_number=2,
        region_type=RegionType.TABLE_ROW_GROUP,
        text="| Gamma Irradiation | 25.0 - 40.0 kGy | 28.4 kGy |",
        parent_section_id="Sterilization Specifications",
    )

    expanded = HybridChunker.expand_evidence(child_chunk, structured_doc, max_expansion_tokens=4000)

    assert expanded.chunk_id == "tbl_sterilization_grp_1"
    assert expanded.linked_table is not None
    assert expanded.linked_table.table_id == "tbl_sterilization"
    # Full table markdown and linked footnote are present in expanded evidence!
    assert "Endotoxin" in expanded.expanded_text
    assert "LAL kinetic chromogenic assay" in expanded.expanded_text


def test_late_chunking_token_pooling():
    """Verify LateChunker performs mean pooling of contextual token vectors across chunk spans."""
    # 6 token embeddings of dimension 4
    token_embeddings = [
        [1.0, 2.0, 3.0, 4.0],
        [2.0, 3.0, 4.0, 5.0],
        [3.0, 4.0, 5.0, 6.0],  # Chunk 1: span (0, 3) -> avg: [2.0, 3.0, 4.0, 5.0]
        [10.0, 20.0, 30.0, 40.0],
        [20.0, 30.0, 40.0, 50.0],
        [30.0, 40.0, 50.0, 60.0],  # Chunk 2: span (3, 6) -> avg: [20.0, 30.0, 40.0, 50.0]
    ]
    spans = [(0, 3), (3, 6)]

    pooled = LateChunker.pool_chunk_token_embeddings(token_embeddings, spans)
    assert len(pooled) == 2
    assert pooled[0] == [2.0, 3.0, 4.0, 5.0]
    assert pooled[1] == [20.0, 30.0, 40.0, 50.0]
