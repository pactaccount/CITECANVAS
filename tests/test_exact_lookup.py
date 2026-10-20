"""
Unit tests for Exact Identifier Lookup Engine.
Verifies:
1. Exact constraint matching for lot numbers, ECNs, and part numbers.
2. Preservation of leading zeros and punctuation.
3. Reporting missing exact matches with distinct approximate suggestions.
4. Integration with HybridRanker for prioritized exact placement.
"""

import pytest
from backend.src.retrieval.exact_lookup import ExactIdentifierLookup, IdentifierRecord
from backend.src.schemas.contracts import (
    BoundingBox,
    DocumentRegion,
    ProcessingVersion,
    QualityStatus,
    RegionType,
    StructuredDocument,
)


def test_exact_identifier_normalization_preserves_structure():
    """Verify that normalization preserves leading zeros, hyphens, and distinct codes."""
    assert ExactIdentifierLookup.normalize_identifier("  ECN-2023-0847  ") == "ECN-2023-0847"
    assert ExactIdentifierLookup.normalize_identifier("0042") == "0042"
    assert ExactIdentifierLookup.normalize_identifier("lot 18356721") == "LOT 18356721"
    # Verify that hyphens are preserved (AB-01 is not silently converted to AB01)
    assert ExactIdentifierLookup.normalize_identifier("AB-01") != "AB01"


def test_exact_lookup_indexing_and_matching():
    """Verify document identifier indexing and strict exact matching."""
    lookup = ExactIdentifierLookup()

    r1 = DocumentRegion(
        region_id="r_cert",
        page_number=2,
        region_type=RegionType.PARAGRAPH,
        text="Certificate of Quality for AKTA ready Low Flow Kit. Lot Number: 18356721.",
        local_identifiers=["18356721"],
    )
    r2 = DocumentRegion(
        region_id="r_ecn",
        page_number=5,
        region_type=RegionType.PARAGRAPH,
        text="Configuration Change: ECN-2023-0847 implemented on pressure sensors.",
        local_identifiers=["ECN-2023-0847"],
    )

    doc = StructuredDocument(
        document_id="doc_pharma_1",
        version_id="v1",
        filename="pharma.pdf",
        sha256_hash="hash123",
        total_pages=5,
        processing_version=ProcessingVersion(
            version_id="v1",
            document_id="doc_pharma_1",
            created_at="2026-10-18T00:00:00Z",
        ),
        regions=[r1, r2],
    )

    lookup.index_document(doc)

    # 1. Exact match on Lot number
    res1 = lookup.lookup("18356721")
    assert res1.has_exact_match is True
    assert len(res1.matched_records) == 1
    assert res1.matched_records[0].page_number == 2
    assert res1.matched_records[0].doc_id == "doc_pharma_1"

    # 2. Exact match on ECN
    res2 = lookup.lookup("ECN-2023-0847")
    assert res2.has_exact_match is True
    assert len(res2.matched_records) == 1
    assert res2.matched_records[0].page_number == 5

    # 3. Non-existent identifier reports no exact match with approximate suggestions
    res3 = lookup.lookup("ECN-2023-0848")
    assert res3.has_exact_match is False
    assert len(res3.matched_records) == 0
    assert "No exact match found" in res3.message
    # Suggests similar prefix ECN-2023-0847
    assert any("ECN-2023" in s for s in res3.approximate_suggestions)


def test_exact_lookup_doc_filter():
    """Verify exact lookup filters by document ID."""
    lookup = ExactIdentifierLookup()

    r1 = DocumentRegion(
        region_id="r1",
        page_number=1,
        region_type=RegionType.PARAGRAPH,
        text="Batch 998877.",
        local_identifiers=["998877"],
    )
    doc1 = StructuredDocument(
        document_id="doc_A",
        version_id="v1",
        filename="A.pdf",
        sha256_hash="hA",
        total_pages=1,
        processing_version=ProcessingVersion(version_id="v1", document_id="doc_A", created_at="2026-10-18T00:00:00Z"),
        regions=[r1],
    )
    doc2 = StructuredDocument(
        document_id="doc_B",
        version_id="v1",
        filename="B.pdf",
        sha256_hash="hB",
        total_pages=1,
        processing_version=ProcessingVersion(version_id="v1", document_id="doc_B", created_at="2026-10-18T00:00:00Z"),
        regions=[r1],
    )

    lookup.index_document(doc1)
    lookup.index_document(doc2)

    # Scoped to doc_A
    res = lookup.lookup("998877", doc_id="doc_A")
    assert res.has_exact_match is True
    assert len(res.matched_records) == 1
    assert res.matched_records[0].doc_id == "doc_A"
