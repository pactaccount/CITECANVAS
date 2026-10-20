"""
Unit tests for QueryProcessor and Structured Query Planning.
Verifies:
1. Immutable protected spans (codes, quantities with units, dates).
2. Conversation-aware rewriting (resolving anaphora, detecting ambiguity).
3. StructuredQueryPlan generation with isolated sub-query constraints (Rev B vs Rev C).
4. Non-destructive vocabulary expansion (original terms preserved).
5. Validated metadata filtering (hard constraints vs soft preferences).
6. Evidence coverage checking and bounded retrieval repair.
"""

import pytest
from backend.src.retrieval.query_processor import (
    QueryProcessor,
    StructuredQueryPlan,
    TaskType,
    TaskFacet,
    DependencyType,
    CoverageReport,
)


def test_immutable_protected_spans():
    """Verify codes, numbers with units, and dates are identified as protected spans."""
    query = "Verify that ECN-2023-0847 maintains operating pressure at 3.0 bar for Lot 18356721."
    spans = QueryProcessor.extract_protected_spans(query)
    span_texts = [s.text for s in spans]

    assert "ECN-2023-0847" in span_texts
    assert "3.0 bar" in span_texts
    assert any("18356721" in s for s in span_texts)


def test_conversation_aware_rewriting():
    """Verify conversational references are resolved using prior context."""
    history = [
        {"role": "user", "content": "What are the specifications for the AKTA ready M-210 manual in Revision C?"},
        {"role": "assistant", "content": "Revision C specifies operating pressure at 3.0 bar and gamma dose 25.0 - 40.0 kGy."},
    ]

    # Follow-up question referring to 'the previous revision'
    rewritten, is_ambiguous, unresolved = QueryProcessor.rewrite_conversational_references(
        query="What was the pressure limit in the previous revision?",
        conversation_context=history,
    )
    assert "Revision B" in rewritten
    assert is_ambiguous is False
    assert len(unresolved) == 0

    # Ambiguous follow-up without history
    rewritten_raw, is_ambig_raw, unres_raw = QueryProcessor.rewrite_conversational_references(
        query="What about the previous revision?",
        conversation_context=[],
    )
    assert is_ambig_raw is True
    assert len(unres_raw) > 0


def test_structured_query_plan_comparison_and_subqueries():
    """
    Verify comparison query plan generates independent subqueries with per-subquery constraints.
    Ensures Rev B vs Rev C does NOT create an impossible global filter 'revision=B AND revision=C'.
    """
    query = "Compare the maximum operating pressure in Rev B and Rev C of the M-210 manual, and show the supporting table rows."
    plan = QueryProcessor.parse_plan(query, active_document="M-210 manual")

    assert plan.task_type == TaskType.COMPARISON
    assert TaskFacet.COMPARATIVE in plan.facets
    assert TaskFacet.NUMERIC_METRICS in plan.facets
    assert plan.hard_constraints.get("doc_id") == "M-210 manual"

    # Must generate 2 independent subqueries
    assert len(plan.sub_queries) == 2
    sq1 = plan.sub_queries[0]
    sq2 = plan.sub_queries[1]

    # Each subquery must have its own isolated revision constraint!
    assert sq1.hard_constraints.get("revision") == "B"
    assert sq2.hard_constraints.get("revision") == "C"
    assert sq1.dependency_type == DependencyType.PARALLEL

    # Evidence requirements must specify both comparison groups
    assert "Revision B" in plan.evidence_requirements.comparison_groups
    assert "Revision C" in plan.evidence_requirements.comparison_groups
    assert plan.evidence_requirements.requires_table_rows is True


def test_non_destructive_vocabulary_expansion():
    """Verify domain expansion appends alternatives without destroying the original text."""
    query = "Verify WFI rinse and LAL endotoxin testing limits"
    expanded = QueryProcessor.expand_vocabulary_non_destructively(query)

    # Original wording MUST be preserved!
    assert "Verify WFI rinse and LAL endotoxin testing limits" in expanded
    # Supported meanings must be appended
    assert "water for injection" in expanded
    assert "limulus amebocyte lysate endotoxin assay" in expanded


def test_evidence_coverage_checking_and_repair():
    """Verify evidence coverage detects missing comparison sides and triggers targeted repair."""
    query = "Compare operating pressure between Revision B and Revision C"
    plan = QueryProcessor.parse_plan(query)

    # Scenario 1: Only Revision B evidence retrieved (partial retrieval)
    partial_evidence = [
        "In Revision B, the single-use flow kit operates up to a maximum pressure of 2.5 bar.",
    ]
    report = QueryProcessor.check_evidence_coverage(plan, partial_evidence)

    assert report.is_complete is False
    assert "Revision C" in report.missing_aspects
    assert "Revision B" in report.satisfied_aspects
    assert report.repair_query is not None
    assert "Revision C" in report.repair_query

    # Scenario 2: Both Revision B and Revision C evidence retrieved (complete)
    complete_evidence = [
        "In Revision B, maximum pressure is 2.5 bar.",
        "In Revision C, upgraded reinforced tubing raises operating pressure to 3.0 bar.",
    ]
    report_complete = QueryProcessor.check_evidence_coverage(plan, complete_evidence)
    assert report_complete.is_complete is True
    assert len(report_complete.missing_aspects) == 0
