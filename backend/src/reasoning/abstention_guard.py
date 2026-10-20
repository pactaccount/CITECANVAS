"""
Deterministic Abstention Guardrail.
Validates that generated claims are strictly anchored by visual citations,
and forces an explicit refusal (status: 'abstain') when evidence is missing or ambiguous.
"""

from typing import Optional
from backend.src.schemas.contracts import CitationStatus, GroundedAnswer


class AbstentionGuard:
    """
    Enterprise guardrail ensuring zero-hallucination compliance.
    Rejects unsupported assertions and validates visual citations.
    """

    @staticmethod
    def verify_answer(
        answer: GroundedAnswer,
        min_confidence: float = 0.70,
    ) -> GroundedAnswer:
        """
        Enforces enterprise invariants on a generated answer:
        1. If status is 'direct', a visual citation and bounding box must exist.
        2. If confidence is below min_confidence, demotes to 'abstain'.
        3. If status is 'abstain', ensures an explanatory reason is present.
        """
        if answer.status == CitationStatus.DIRECT:
            if not answer.citation or not answer.citation.box_2d:
                # If no citation box was localized, demote to abstain
                return GroundedAnswer(
                    query=answer.query,
                    status=CitationStatus.ABSTAIN,
                    abstention_reason="Answer lacked verifiable visual bounding box citation.",
                    latency_ms=answer.latency_ms,
                    model_id=answer.model_id,
                )

            if answer.citation.confidence_score < min_confidence:
                return GroundedAnswer(
                    query=answer.query,
                    status=CitationStatus.ABSTAIN,
                    abstention_reason=f"Grounding confidence ({answer.citation.confidence_score:.2f}) was below enterprise threshold ({min_confidence:.2f}).",
                    latency_ms=answer.latency_ms,
                    model_id=answer.model_id,
                )

        elif answer.status == CitationStatus.ABSTAIN:
            if not answer.abstention_reason:
                answer.abstention_reason = "Information requested is not reported in the document."

        return answer
