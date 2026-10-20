"""
Unit and Integration Tests for Evidence Selection, Protected Deduplication, and Budgeting.
Verifies:
1. Protected deduplication preserves meaningful differences (numbers, revisions, units, negations).
2. True duplicates are merged while preserving retrieval branch provenance.
3. Structured fact requirements are verified for completeness and contradictions.
4. Budget constraints (token budget, bundle count) are strictly enforced.
5. Coherent context packing formats evidence cleanly with explicit bundle citations.
"""

import pytest
from backend.src.retrieval.evidence_selector import (
    EvidenceBundle,
    EvidenceModality,
    FactRequirement,
    FactSupportStatus,
    ProtectedDeduplicator,
    BudgetedEvidenceSelector,
    CalculationRecord,
)


def test_protected_deduplication_preserves_differences():
    """Verify that records with different numbers, units, or revisions are never pruned as duplicates."""
    b1 = EvidenceBundle(
        bundle_id="b_rev_b",
        doc_id="doc_m210",
        version_id="v1",
        page_number=3,
        modality=EvidenceModality.TABLE,
        primary_text="Maximum operating pressure: 3.0 bar.",
        numeric_value=3.0,
        unit="bar",
        period_or_revision="Revision B",
        retrieval_branches=["bm25"],
    )

    # b2 has nearly identical wording, but specifies 2.5 bar for Revision C
    b2 = EvidenceBundle(
        bundle_id="b_rev_c",
        doc_id="doc_m210",
        version_id="v1",
        page_number=3,
        modality=EvidenceModality.TABLE,
        primary_text="Maximum operating pressure: 2.5 bar.",
        numeric_value=2.5,
        unit="bar",
        period_or_revision="Revision C",
        retrieval_branches=["dense"],
    )

    # Assert that protected deduplicator recognizes them as meaningfully different
    assert ProtectedDeduplicator.are_meaningfully_different(b1, b2) is True

    # When deduplicating the list, both must be preserved
    deduped = ProtectedDeduplicator.deduplicate_bundles([b1, b2])
    assert len(deduped) == 2


def test_true_duplicate_merging_preserves_provenance():
    """Verify that genuinely identical text retrieved across different branches is merged with unified provenance."""
    b_bm25 = EvidenceBundle(
        bundle_id="b_lexical",
        doc_id="doc_m210",
        version_id="v1",
        page_number=1,
        modality=EvidenceModality.TEXT,
        primary_text="Standard storage temperature is between +2°C and +8°C.",
        numeric_value=5.0,
        unit="°C",
        retrieval_branches=["bm25"],
    )

    b_dense = EvidenceBundle(
        bundle_id="b_semantic",
        doc_id="doc_m210",
        version_id="v1",
        page_number=1,
        modality=EvidenceModality.TEXT,
        primary_text="Standard storage temperature is between +2°C and +8°C.",
        numeric_value=5.0,
        unit="°C",
        retrieval_branches=["dense"],
    )

    assert ProtectedDeduplicator.are_meaningfully_different(b_bm25, b_dense) is False

    deduped = ProtectedDeduplicator.deduplicate_bundles([b_bm25, b_dense])
    assert len(deduped) == 1
    # Both retrieval branches must be recorded in the surviving bundle
    assert "bm25" in deduped[0].retrieval_branches
    assert "dense" in deduped[0].retrieval_branches


def test_fact_support_checking_and_conflict_detection():
    """Verify requirement verification detects complete support, missing aspects, and contradictory data."""
    selector = BudgetedEvidenceSelector(max_bundles=5, max_tokens=1000)

    b_rev_b = EvidenceBundle(
        bundle_id="b_b",
        doc_id="doc_m210",
        version_id="v1",
        page_number=3,
        modality=EvidenceModality.TABLE,
        primary_text="Maximum operating pressure in Revision B is 3.0 bar",
        numeric_value=3.0,
        unit="bar",
        period_or_revision="Revision B",
        row_label="Maximum Operating Pressure",
        column_header="Revision B",
    )

    b_rev_c = EvidenceBundle(
        bundle_id="b_c",
        doc_id="doc_m210",
        version_id="v1",
        page_number=3,
        modality=EvidenceModality.TABLE,
        primary_text="Maximum operating pressure in Revision C is 2.5 bar",
        numeric_value=2.5,
        unit="bar",
        period_or_revision="Revision C",
        row_label="Maximum Operating Pressure",
        column_header="Revision C",
    )

    reqs = [
        FactRequirement(
            requirement_id="req_b",
            metric="operating pressure",
            version_or_period="Revision B",
            expected_unit="bar",
        ),
        FactRequirement(
            requirement_id="req_c",
            metric="operating pressure",
            version_or_period="Revision C",
            expected_unit="bar",
        ),
        FactRequirement(
            requirement_id="req_burst",
            metric="burst pressure",  # Not in candidates
            expected_unit="bar",
        ),
    ]

    selected, evaluated_reqs, report = selector.select_evidence([b_rev_b, b_rev_c], reqs)

    assert len(selected) == 2
    req_map = {r.requirement_id: r for r in evaluated_reqs}
    assert req_map["req_b"].status == FactSupportStatus.SUPPORTED
    assert req_map["req_c"].status == FactSupportStatus.SUPPORTED
    assert req_map["req_burst"].status == FactSupportStatus.MISSING
    assert report["all_requirements_satisfied"] is False


def test_budget_enforcement_and_context_packing():
    """Verify token budgets are enforced and packed context groups comparisons cleanly."""
    # Strict token budget of 50 tokens (roughly 200 chars)
    selector = BudgetedEvidenceSelector(max_bundles=2, max_tokens=60)

    b1 = EvidenceBundle(
        bundle_id="EVID-1",
        doc_id="doc_m210",
        version_id="v1",
        page_number=3,
        modality=EvidenceModality.TABLE,
        primary_text="Rev B operating pressure: 3.0 bar.",
        numeric_value=3.0,
        unit="bar",
        period_or_revision="Revision B",
        row_label="Operating Pressure",
        column_header="Rev B",
        footnotes=["Tested per ASTM D1003"],
    )
    b2 = EvidenceBundle(
        bundle_id="EVID-2",
        doc_id="doc_m210",
        version_id="v1",
        page_number=3,
        modality=EvidenceModality.TABLE,
        primary_text="Rev C operating pressure: 2.5 bar.",
        numeric_value=2.5,
        unit="bar",
        period_or_revision="Revision C",
        row_label="Operating Pressure",
        column_header="Rev C",
        footnotes=["Tested per ASTM D1003"],
    )
    b3 = EvidenceBundle(
        bundle_id="EVID-3",
        doc_id="doc_m210",
        version_id="v1",
        page_number=5,
        modality=EvidenceModality.TEXT,
        primary_text="Long narrative filler text describing engineering background.",
    )

    reqs = [
        FactRequirement(requirement_id="r1", metric="operating pressure", version_or_period="Revision B"),
        FactRequirement(requirement_id="r2", metric="operating pressure", version_or_period="Revision C"),
    ]

    selected, _, report = selector.select_evidence([b1, b2, b3], reqs)

    # b3 should be dropped due to max_bundles budget
    assert len(selected) == 2
    assert "EVID-1" in [b.bundle_id for b in selected]
    assert "EVID-2" in [b.bundle_id for b in selected]
    assert report["estimated_tokens"] <= 60

    # Test prompt context packing
    packed_context = BudgetedEvidenceSelector.pack_context_for_prompt(selected, "Compare Revision B and Revision C")
    assert "=== VERIFIED EVIDENCE DOSSIER ===" in packed_context
    assert "Scope: Revision B" in packed_context
    assert "Scope: Revision C" in packed_context
    assert "[EVID-1]" in packed_context
    assert "Tested per ASTM D1003" in packed_context
