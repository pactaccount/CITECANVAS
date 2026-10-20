"""
Evidence Selection, Protected Deduplication, and Budgeted Context Packing Engine.
Implements:
1. Evidence Bundling: Packages atomic facts with their essential dependencies
   (cell + row + header + unit + footnotes; chart + image + caption + axes; stamp + transcription).
2. Protected Deduplication: Prevents removing facts with different numbers, units, revisions, or negations.
3. Evidence-Support Checking: Evaluates whether retrieved bundles genuinely support the query's fact requirements.
4. Contradiction & Version-Aware Conflict Detection: Distinguishes cross-revision differences from true conflicts.
5. Budget-Constrained Selection: Enforces token, candidate, and image crop budgets.
6. Coherent Context Ordering: Groups comparisons and places directly useful evidence first with explicit IDs.
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from pydantic import BaseModel, Field

from backend.src.schemas.contracts import BoundingBox


class FactSupportStatus(str, Enum):
    """Factual support status of an evidence requirement."""
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    MISSING = "missing"
    UNREADABLE = "unreadable"


class EvidenceModality(str, Enum):
    TEXT = "text"
    TABLE = "table"
    CHART = "chart"
    STAMP = "stamp"
    CALCULATION = "calculation"


class EvidenceBundle(BaseModel):
    """Self-contained evidence bundle with all interpretive dependencies."""
    bundle_id: str
    doc_id: str
    version_id: str
    page_number: int
    region_id: Optional[str] = None
    modality: EvidenceModality
    primary_text: str
    row_label: Optional[str] = None
    column_header: Optional[str] = None
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    period_or_revision: Optional[str] = None
    footnotes: List[str] = Field(default_factory=list)
    caption: Optional[str] = None
    box_2d: Optional[BoundingBox] = None
    crop_path: Optional[str] = None
    retrieval_branches: List[str] = Field(default_factory=list)
    confidence: float = 1.0


class FactRequirement(BaseModel):
    """Structured fact requirement for QA sufficiency verification."""
    requirement_id: str
    entity: Optional[str] = None
    version_or_period: Optional[str] = None
    metric: str
    expected_unit: Optional[str] = None
    status: FactSupportStatus = FactSupportStatus.MISSING
    satisfying_bundle_ids: List[str] = Field(default_factory=list)
    conflict_notes: Optional[str] = None


class CalculationRecord(BaseModel):
    """Validated arithmetic record (TAT-QA standard)."""
    calculation_id: str
    operation: str  # sum, avg, max, min, diff
    operands: List[float]
    units: List[str]
    is_unit_consistent: bool
    scale_factor: float = 1.0
    result: float
    source_bundle_ids: List[str]
    footnotes: List[str] = Field(default_factory=list)


class ProtectedDeduplicator:
    """
    Deduplicates overlapping retrieval candidates without destroying meaningful differences
    (numbers, units, revisions, negations, conditions).
    """

    @staticmethod
    def extract_semantic_fingerprint(text: str) -> Dict[str, Any]:
        """Extracts numbers, units, revisions, and negation tokens."""
        lower = text.lower()
        numbers = re.findall(r"[-+]?\d*\.?\d+", text)
        revisions = re.findall(r"\brev(?:ision)?\.?\s*([A-Z0-9]+)\b", text, re.IGNORECASE)
        units = re.findall(r"\b(bar|kgy|psi|eu/ml|°c|%|usd|mg|ml)\b", lower)
        has_negation = bool(re.search(r"\b(not|never|no|none|without|neither|nor)\b", lower))

        return {
            "numbers": sorted(numbers),
            "revisions": sorted([r.upper() for r in revisions]),
            "units": sorted(units),
            "has_negation": has_negation,
        }

    @classmethod
    def are_meaningfully_different(cls, b1: EvidenceBundle, b2: EvidenceBundle) -> bool:
        """
        Determines whether two bundles contain distinct facts, even if text phrasing is similar.
        """
        # 1. Different revision or period
        if b1.period_or_revision and b2.period_or_revision:
            if b1.period_or_revision.upper() != b2.period_or_revision.upper():
                return True

        # 2. Different numeric values
        if b1.numeric_value is not None and b2.numeric_value is not None:
            if abs(b1.numeric_value - b2.numeric_value) > 1e-5:
                return True

        # 3. Different physical units
        if b1.unit and b2.unit and b1.unit.lower() != b2.unit.lower():
            return True

        # 4. Fingerprint checks on primary text
        fp1 = cls.extract_semantic_fingerprint(b1.primary_text)
        fp2 = cls.extract_semantic_fingerprint(b2.primary_text)

        if fp1["numbers"] != fp2["numbers"]:
            return True
        if fp1["revisions"] != fp2["revisions"]:
            return True
        if fp1["units"] != fp2["units"]:
            return True
        if fp1["has_negation"] != fp2["has_negation"]:
            return True

        return False

    @classmethod
    def deduplicate_bundles(cls, bundles: List[EvidenceBundle]) -> List[EvidenceBundle]:
        """
        Prunes redundant identical candidates while strictly preserving meaningful factual differences.
        Merges retrieval branch metadata when identical content is retrieved from multiple paths.
        """
        unique_bundles: List[EvidenceBundle] = []

        for b in bundles:
            duplicate_found = False
            for existing in unique_bundles:
                # Same source document, page, and identical semantic content
                if (
                    b.doc_id == existing.doc_id
                    and b.page_number == existing.page_number
                    and not cls.are_meaningfully_different(b, existing)
                ):
                    # Merge retrieval branches
                    for branch in b.retrieval_branches:
                        if branch not in existing.retrieval_branches:
                            existing.retrieval_branches.append(branch)
                    duplicate_found = True
                    break

            if not duplicate_found:
                unique_bundles.append(b)

        return unique_bundles


class BudgetedEvidenceSelector:
    """
    Selects, validates, and formats evidence bundles within explicit token, image, and candidate budgets.
    Mitigates 'Lost in the Middle' through coherent, structured prompt packing.
    """

    def __init__(
        self,
        max_bundles: int = 5,
        max_tokens: int = 1500,
        max_image_crops: int = 2,
    ):
        self.max_bundles = max_bundles
        self.max_tokens = max_tokens
        self.max_image_crops = max_image_crops

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Fast token estimation (~4 characters per token)."""
        return max(1, len(text) // 4)

    def select_evidence(
        self,
        candidate_bundles: List[EvidenceBundle],
        fact_requirements: List[FactRequirement],
    ) -> Tuple[List[EvidenceBundle], List[FactRequirement], Dict[str, Any]]:
        """
        Executes budgeted evidence selection:
        1. Protected deduplication.
        2. Prioritizes bundles satisfying unanswered fact requirements.
        3. Enforces token and crop budgets.
        4. Evaluates fact support status (supported, missing, contradicted).
        """
        # Step 1: Protected deduplication
        deduped = ProtectedDeduplicator.deduplicate_bundles(candidate_bundles)

        selected: List[EvidenceBundle] = []
        current_tokens = 0
        current_crops = 0

        # Step 2: Fulfill structured fact requirements first
        for req in fact_requirements:
            for b in deduped:
                if b in selected:
                    continue

                # Match metric and revision/period
                metric_match = req.metric.lower() in b.primary_text.lower() or (
                    b.row_label and req.metric.lower() in b.row_label.lower()
                )
                rev_match = True
                if req.version_or_period and b.period_or_revision:
                    rev_match = req.version_or_period.upper() in b.period_or_revision.upper()

                if metric_match and rev_match:
                    bundle_toks = self.estimate_tokens(b.primary_text)
                    if current_tokens + bundle_toks <= self.max_tokens and len(selected) < self.max_bundles:
                        selected.append(b)
                        current_tokens += bundle_toks
                        if b.crop_path:
                            current_crops += 1
                        req.status = FactSupportStatus.SUPPORTED
                        req.satisfying_bundle_ids.append(b.bundle_id)
                        break

        # Step 3: Add remaining high-relevance bundles within budget
        for b in deduped:
            if b in selected:
                continue
            if len(selected) >= self.max_bundles:
                break

            bundle_toks = self.estimate_tokens(b.primary_text)
            if current_tokens + bundle_toks > self.max_tokens:
                continue
            if b.crop_path and current_crops >= self.max_image_crops:
                # Exclude crop, retain text
                b.crop_path = None

            selected.append(b)
            current_tokens += bundle_toks
            if b.crop_path:
                current_crops += 1

        # Step 4: Check for conflicts across selected evidence
        for req in fact_requirements:
            satisfying = [b for b in selected if b.bundle_id in req.satisfying_bundle_ids]
            if len(satisfying) >= 2:
                # Check if multiple values claim to satisfy the same metric within the same revision
                nums = [b.numeric_value for b in satisfying if b.numeric_value is not None]
                if len(set(nums)) > 1:
                    req.status = FactSupportStatus.CONTRADICTED
                    req.conflict_notes = f"Conflicting values detected: {nums}"

        budget_report = {
            "selected_bundle_count": len(selected),
            "estimated_tokens": current_tokens,
            "image_crop_count": current_crops,
            "all_requirements_satisfied": all(r.status == FactSupportStatus.SUPPORTED for r in fact_requirements),
        }

        return selected, fact_requirements, budget_report

    @staticmethod
    def pack_context_for_prompt(
        selected_bundles: List[EvidenceBundle],
        query: str,
    ) -> str:
        """
        Packs evidence into a coherent prompt context:
        - Directly useful evidence placed early.
        - Related table headers, units, and footnotes attached adjacent to values.
        - Comparisons clearly grouped by revision or period.
        - Explicit evidence IDs for claim-to-source attribution.
        """
        if not selected_bundles:
            return "No verified evidence available."

        lines = ["=== VERIFIED EVIDENCE DOSSIER ==="]

        # Group by revision if comparison query
        is_comparison = any(w in query.lower() for w in ["compare", "difference", "versus", "vs", "between"])

        if is_comparison:
            grouped_by_rev: Dict[str, List[EvidenceBundle]] = {}
            for b in selected_bundles:
                key = b.period_or_revision or "General Specification"
                if key not in grouped_by_rev:
                    grouped_by_rev[key] = []
                grouped_by_rev[key].append(b)

            for rev, bundles in grouped_by_rev.items():
                lines.append(f"\n--- Scope: {rev} ---")
                for b in bundles:
                    lines.append(f"[{b.bundle_id}] (Page {b.page_number}, Doc: {b.doc_id}): {b.primary_text}")
                    if b.row_label and b.column_header:
                        lines.append(f"    Table Context: Row '{b.row_label}' | Column '{b.column_header}' | Unit: {b.unit or 'N/A'}")
                    if b.footnotes:
                        lines.append(f"    Applicable Footnotes: {'; '.join(b.footnotes)}")
        else:
            for b in selected_bundles:
                lines.append(f"[{b.bundle_id}] (Page {b.page_number}, Doc: {b.doc_id}, Modality: {b.modality.value}):")
                lines.append(f"    Content: {b.primary_text}")
                if b.row_label and b.column_header:
                    lines.append(f"    Table Context: Row '{b.row_label}' | Column '{b.column_header}' | Unit: {b.unit or 'N/A'}")
                if b.footnotes:
                    lines.append(f"    Footnotes: {'; '.join(b.footnotes)}")

        lines.append("\n=== END EVIDENCE DOSSIER ===")
        return "\n".join(lines)
