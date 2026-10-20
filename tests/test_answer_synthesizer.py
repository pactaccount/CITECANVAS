"""
Unit and Integration Tests for Answer Synthesizer, Typed Facts, and Deterministic Arithmetic.
Verifies:
1. Range values (e.g. 25.0 - 40.0 kGy) are preserved in full rather than truncated to a single float.
2. Financial values preserve currency, scale (millions), and period.
3. Deterministic pressure conversion executes with NIST precision (350 psi ≈ 24.13 bar, ~14.5x ratio).
4. Claim-level support checking validates candidate facts against original evidence.
5. Calibrated multi-outcome abstention produces explicit outcomes (complete, partial, insufficient_evidence).
"""

import pytest
from backend.src.schemas.contracts import BoundingBox, CitationStatus
from backend.src.retrieval.evidence_selector import EvidenceBundle, EvidenceModality
from backend.src.reasoning.answer_synthesizer import (
    AnswerSpecification,
    AnswerType,
    CalibratedAnswerSynthesizer,
    DeterministicArithmeticTool,
    FactSupportVerifier,
    FinancialAmount,
    RangeValue,
    TypedFact,
)


def test_range_value_preservation_not_truncated():
    """Verify that a dose range (25.0 - 40.0 kGy) preserves both lower and upper bounds."""
    spec = AnswerSpecification(
        requested_info="Gamma irradiation dose range",
        expected_answer_type=AnswerType.RANGE,
    )

    range_fact = TypedFact(
        claim_id="c_dose",
        fact_type=AnswerType.RANGE,
        raw_text="The specified gamma irradiation dose range is 25.0 - 40.0 kGy",
        range_value=RangeValue(lower=25.0, upper=40.0, unit="kGy", raw_text="25.0 - 40.0 kGy"),
        evidence_refs=["EVID-1"],
    )

    source_bundle = EvidenceBundle(
        bundle_id="EVID-1",
        doc_id="doc_pharma_1",
        version_id="v1",
        page_number=3,
        modality=EvidenceModality.TABLE,
        primary_text="Gamma irradiation dose specification: 25.0 - 40.0 kGy for inlet line.",
        box_2d=BoundingBox(ymin=365, xmin=315, ymax=415, xmax=465),
    )

    answer = CalibratedAnswerSynthesizer.synthesize_answer(
        query="What is the gamma dose range?",
        spec=spec,
        facts=[range_fact],
        evidence_bundles=[source_bundle],
    )

    assert answer.status == CitationStatus.DIRECT
    assert answer.outcome_type == "complete"
    # CRITICAL: Verify range is preserved as a tuple (25.0, 40.0), not collapsed to 25.0
    assert answer.range_value == (25.0, 40.0)
    assert answer.unit == "kGy"
    assert "EVID-1" in answer.claim_citations
    assert "[EVID-1]" in answer.answer


def test_financial_amount_preservation():
    """Verify that financial values preserve currency, scale (millions), and period."""
    spec = AnswerSpecification(
        requested_info="Automotive regulatory credits revenue",
        target_period="Q3 2023",
        expected_answer_type=AnswerType.FINANCIAL_AMOUNT,
    )

    fin_fact = TypedFact(
        claim_id="c_fin",
        fact_type=AnswerType.FINANCIAL_AMOUNT,
        raw_text="Automotive regulatory credits revenue was $554 million in Q3 2023",
        financial_value=FinancialAmount(
            amount=554.0,
            currency="USD",
            scale="millions",
            period="Q3 2023",
            raw_text="$554 million",
        ),
        evidence_refs=["EVID-SEC"],
    )

    sec_bundle = EvidenceBundle(
        bundle_id="EVID-SEC",
        doc_id="tsla_10q_q3_2023",
        version_id="v1",
        page_number=4,
        modality=EvidenceModality.TABLE,
        primary_text="Automotive regulatory credits: $554 million for three months ended September 30, 2023.",
        numeric_value=554.0,
        unit="USD Millions",
        box_2d=BoundingBox(ymin=380, xmin=120, ymax=440, xmax=850),
    )

    answer = CalibratedAnswerSynthesizer.synthesize_answer(
        query="What was regulatory credit revenue in Q3 2023?",
        spec=spec,
        facts=[fin_fact],
        evidence_bundles=[sec_bundle],
    )

    assert answer.status == CitationStatus.DIRECT
    assert answer.financial_amount is not None
    assert answer.financial_amount["amount"] == 554.0
    assert answer.financial_amount["currency"] == "USD"
    assert answer.financial_amount["scale"] == "millions"
    assert answer.financial_amount["period"] == "Q3 2023"


def test_deterministic_pressure_conversion_nist():
    """Verify exact NIST pressure conversion: 350 psi is approximately 24.13 bar (~14.5x difference)."""
    # 350 psi to bar
    conv = DeterministicArithmeticTool.convert_pressure(350.0, from_unit="psi", to_unit="bar")
    assert conv["input_value"] == 350.0
    # 350 * 0.0689475729 = 24.13165 bar
    assert abs(conv["result"] - 24.1316) < 1e-3
    assert conv["result_unit"] == "bar"

    # Percentage change
    pct = DeterministicArithmeticTool.calculate_percentage_change(200.0, 250.0)
    assert pct["percentage_change"] == 25.0


def test_claim_support_verification_catches_unbacked_facts():
    """Verify that candidate facts lacking evidence support are marked unverified and cause abstention."""
    spec = AnswerSpecification(
        requested_info="Burst pressure specification",
        expected_answer_type=AnswerType.SCALAR,
    )

    unbacked_fact = TypedFact(
        claim_id="c_hallucinated",
        fact_type=AnswerType.SCALAR,
        raw_text="The burst pressure is 500 bar",
        scalar_value=500.0,
        unit="bar",
        evidence_refs=["EVID-MISSING"],
    )

    # Candidate bundle has nothing about 500 bar
    unrelated_bundle = EvidenceBundle(
        bundle_id="EVID-OTHER",
        doc_id="doc_m210",
        version_id="v1",
        page_number=1,
        modality=EvidenceModality.TEXT,
        primary_text="General installation instructions for model M-210.",
    )

    answer = CalibratedAnswerSynthesizer.synthesize_answer(
        query="What is the burst pressure?",
        spec=spec,
        facts=[unbacked_fact],
        evidence_bundles=[unrelated_bundle],
    )

    # Must cleanly abstain rather than hallucinating the 500 bar claim
    assert answer.status == CitationStatus.ABSTAIN
    assert answer.outcome_type == "insufficient_evidence"
    assert "could not be verified" in answer.abstention_reason
