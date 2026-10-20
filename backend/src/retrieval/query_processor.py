"""
Structured Query Planning & Understanding Engine.
Implements the 10-technique query-processing baseline:
1. Protected query normalization with immutable spans (codes, quantities, units, operators).
2. Conversation-aware rewriting (resolves anaphora, detects ambiguity, CONQRR style).
3. Structured query planning (central interface for all retrieval branches).
4. Validated metadata filtering (distinguishes hard constraints, soft preferences, unresolved).
5. Non-destructive vocabulary expansion (preserves original phrasing, appends alternatives).
6. Minimal search rewriting (search-oriented without answer hallucination).
7. Multi-aspect decomposition (parallel vs. sequential dependent multi-hop retrieval).
8. Task-aware multi-faceted routing (allows overlapping facets: comparison + numeric + visual).
9. Evidence-coverage checking (verifies all requested aspects before generation).
10. Bounded retrieval repair (targeted retry for missing aspects based on observable sufficiency).
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.src.schemas.contracts import QualityStatus


class TaskType(str, Enum):
    """Primary operational task."""
    LOOKUP = "lookup"
    COMPARISON = "comparison"
    AGGREGATION = "aggregation"
    VISUAL_INSPECTION = "visual_inspection"
    SUMMARY = "summary"


class TaskFacet(str, Enum):
    """Overlapping query characteristics (non-mutually exclusive)."""
    EXACT_IDENTIFIER = "exact_identifier"
    NUMERIC_METRICS = "numeric_metrics"
    VISUAL_ELEMENTS = "visual_elements"
    COMPARATIVE = "comparative"
    TEMPORAL_VERSIONED = "temporal_versioned"
    PROCEDURAL = "procedural"


class DependencyType(str, Enum):
    """Sub-query execution order."""
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"  # Dependent multi-hop (IRCoT style)


class ConstraintType(str, Enum):
    """Constraint strictness classification."""
    HARD_CONSTRAINT = "hard_constraint"     # Must be strictly enforced in index filtering
    SOFT_PREFERENCE = "soft_preference"     # Inferred guidance, can be relaxed if zero hits
    UNRESOLVED = "unresolved"               # Ambiguous reference needing clarification


class ProtectedSpan(BaseModel):
    """Immutable span that must never be altered or dropped by rewrites."""
    text: str
    span_type: str  # 'code', 'quantity_with_unit', 'date', 'operator', 'quoted'
    start_char: int
    end_char: int


class ValidatedConstraint(BaseModel):
    """Validated metadata constraint."""
    field: str
    value: Any
    constraint_type: ConstraintType
    source_phrase: str
    confidence: float = 1.0


class SubQueryPlan(BaseModel):
    """Independent or sequential sub-query specification."""
    subquery_id: str
    query_text: str
    target_aspect: str
    hard_constraints: Dict[str, Any] = Field(default_factory=dict)
    soft_preferences: Dict[str, Any] = Field(default_factory=dict)
    dependency_type: DependencyType = DependencyType.PARALLEL
    depends_on_subquery_id: Optional[str] = None


class EvidenceRequirements(BaseModel):
    """Explicit checklist of required evidence."""
    required_metrics: List[str] = Field(default_factory=list)
    required_units: List[str] = Field(default_factory=list)
    comparison_groups: List[str] = Field(default_factory=list)
    requires_table_rows: bool = False
    requires_footnotes: bool = False
    requires_visual_crop: bool = False


class BranchRepresentations(BaseModel):
    """Modality-appropriate query representations."""
    exact_lookup_identifiers: List[str] = Field(default_factory=list)
    bm25_query: str
    dense_query: str
    visual_query: str
    structured_filters: Dict[str, Any] = Field(default_factory=dict)


class StructuredQueryPlan(BaseModel):
    """
    The central query planning contract for Evid.
    Coordinates exact lookup, BM25, dense retrieval, visual multi-vectors, and evidence expansion.
    """
    original_query: str
    normalized_query: str
    task_type: TaskType
    facets: List[TaskFacet] = Field(default_factory=list)
    protected_spans: List[ProtectedSpan] = Field(default_factory=list)
    hard_constraints: Dict[str, Any] = Field(default_factory=dict)
    soft_preferences: Dict[str, Any] = Field(default_factory=dict)
    unresolved_constraints: List[str] = Field(default_factory=list)
    sub_queries: List[SubQueryPlan] = Field(default_factory=list)
    evidence_requirements: EvidenceRequirements
    completion_condition: str
    search_representations: BranchRepresentations
    needs_clarification: bool = False
    clarification_prompt: Optional[str] = None


class CoverageReport(BaseModel):
    """Assessment of evidence completeness before answering."""
    is_complete: bool
    missing_aspects: List[str] = Field(default_factory=list)
    satisfied_aspects: List[str] = Field(default_factory=list)
    repair_query: Optional[str] = None
    repair_branch: Optional[str] = None


class QueryProcessor:
    """
    Enterprise query understanding, normalization, planning, and repair engine.
    """

    # Domain vocabulary: adds alternatives without destroying original terms
    DOMAIN_VOCABULARY: Dict[str, str] = {
        "wfi": "water for injection",
        "lal": "limulus amebocyte lysate endotoxin assay",
        "kgy": "kilogray gamma irradiation",
        "ecn": "engineering change notification",
        "usp class vi": "united states pharmacopeia biological reactivity",
        "psi": "pounds per square inch",
        "bar": "bar pressure",
    }

    # Protected span regex patterns
    PROTECTED_PATTERNS = [
        (re.compile(r"\bECN-[0-9]{4}-[0-9]{3,5}\b", re.IGNORECASE), "code"),
        (re.compile(r"\b(?:lot|batch)\s*(?:no\.?|#|number)?\s*[:\-]?\s*([A-Za-z0-9\-]+)", re.IGNORECASE), "code"),
        (re.compile(r"\b[0-9]+(?:\.[0-9]+)?\s*(?:bar|kGy|psi|EU/ml|rpm|°C|USD|%)\b", re.IGNORECASE), "quantity_with_unit"),
        (re.compile(r"\b(?:rev(?:ision)?\.?\s*[A-Z0-9]+)\b", re.IGNORECASE), "code"),
        (re.compile(r"\b(20[12][0-9])\b"), "date"),
        (re.compile(r'"([^"]+)"'), "quoted"),
    ]

    @classmethod
    def extract_protected_spans(cls, text: str) -> List[ProtectedSpan]:
        """Identifies immutable tokens (codes, numbers with units, dates)."""
        spans: List[ProtectedSpan] = []
        STOP_WORDS = {"number", "numbers", "code", "codes", "id", "item", "the", "for", "rev", "page", "lot", "batch"}

        for pat, span_type in cls.PROTECTED_PATTERNS:
            for match in pat.finditer(text):
                val = match.group(0).strip()
                if span_type == "code" and match.lastindex:
                    captured = match.group(1).strip()
                    if captured.lower() in STOP_WORDS:
                        continue
                spans.append(
                    ProtectedSpan(
                        text=val,
                        span_type=span_type,
                        start_char=match.start(),
                        end_char=match.end(),
                    )
                )
        return spans

    @classmethod
    def rewrite_conversational_references(
        cls,
        query: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        active_document: Optional[str] = None,
    ) -> Tuple[str, bool, List[str]]:
        """
        Resolves anaphora ('it', 'that table', 'the previous revision') into standalone queries.
        Returns: (rewritten_query, is_ambiguous, unresolved_notes)
        """
        unresolved: List[str] = []
        rewritten = query.strip()
        q_lower = query.lower()

        # Check for reference to previous revision
        if "previous revision" in q_lower or "earlier version" in q_lower:
            if conversation_context and len(conversation_context) > 0:
                last_turn = conversation_context[-1].get("content", "")
                rev_match = re.search(r"rev(?:ision)?\s*([A-Z0-9]+)", last_turn, re.IGNORECASE)
                if rev_match:
                    current_rev = rev_match.group(1).upper()
                    prev_char = chr(ord(current_rev) - 1) if len(current_rev) == 1 and current_rev > 'A' else "earlier"
                    rewritten = re.sub(r"\b(?:the\s+)?previous revision\b", f"Revision {prev_char}", rewritten, flags=re.IGNORECASE)
                else:
                    unresolved.append("Referenced 'previous revision' without explicit active revision in context.")
            else:
                unresolved.append("Referenced 'previous revision' without conversation history.")

        # Check for vague pronoun 'it'
        if re.search(r"\b(what about it|how does it compare|what is its)\b", q_lower):
            if conversation_context and len(conversation_context) > 0:
                last_turn = conversation_context[-1].get("content", "")
                # Extract main subject
                subject_match = re.search(r"\b(?:for|of|on)\s+([A-Za-z0-9\- ]+?)(?:\?|\.|$)", last_turn)
                if subject_match:
                    subj = subject_match.group(1).strip()
                    rewritten = re.sub(r"\bit\b", subj, rewritten, flags=re.IGNORECASE)
                else:
                    unresolved.append("Ambiguous pronoun 'it' cannot be deterministically resolved.")
            else:
                unresolved.append("Pronoun 'it' used without conversation context.")

        is_ambiguous = len(unresolved) > 0
        return rewritten, is_ambiguous, unresolved

    @classmethod
    def expand_vocabulary_non_destructively(cls, query: str) -> str:
        """
        Appends supported technical meanings while preserving original wording.
        Does NOT replace or destroy original phrases.
        """
        q_lower = query.lower()
        additions = []
        for term, full_meaning in cls.DOMAIN_VOCABULARY.items():
            if re.search(rf"\b{re.escape(term)}\b", q_lower):
                additions.append(full_meaning)

        if additions:
            return f"{query} ({', '.join(additions)})"
        return query

    @classmethod
    def parse_plan(
        cls,
        query: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        active_document: Optional[str] = None,
        known_revisions: Optional[List[str]] = None,
    ) -> StructuredQueryPlan:
        """
        Creates a complete, validated StructuredQueryPlan.
        """
        # 1. Conversation-aware resolution
        rewritten_query, is_ambiguous, unresolved = cls.rewrite_conversational_references(
            query=query,
            conversation_context=conversation_context,
            active_document=active_document,
        )

        # 2. Extract immutable protected spans
        protected_spans = cls.extract_protected_spans(rewritten_query)

        # 3. Classify task type and overlapping facets
        facets: List[TaskFacet] = []
        q_lower = rewritten_query.lower()

        # Check exact codes
        exact_ids = []
        for s in protected_spans:
            if s.span_type == "code":
                exact_ids.append(s.text.strip())
        if exact_ids:
            facets.append(TaskFacet.EXACT_IDENTIFIER)

        if any(s.span_type == "quantity_with_unit" for s in protected_spans) or any(w in q_lower for w in ["limit", "dose", "pressure", "tolerance", "cost", "revenue", "specification"]):
            facets.append(TaskFacet.NUMERIC_METRICS)

        if any(w in q_lower for w in ["chart", "figure", "drawing", "schematic", "graph", "plot", "stamp", "signature", "signed", "diagram"]):
            facets.append(TaskFacet.VISUAL_ELEMENTS)

        is_comp = any(w in q_lower for w in ["compare", "difference", "versus", "vs", "between"]) or re.search(r"rev(?:ision)?\s*[A-Z0-9]+\s+and\s+rev(?:ision)?\s*[A-Z0-9]+", q_lower) is not None
        if is_comp:
            facets.append(TaskFacet.COMPARATIVE)

        if any(s.span_type == "date" for s in protected_spans) or re.search(r"\brev(?:ision)?\b", q_lower):
            facets.append(TaskFacet.TEMPORAL_VERSIONED)

        # Determine primary task
        if is_comp:
            task_type = TaskType.COMPARISON
        elif any(w in q_lower for w in ["total", "sum", "average", "count", "aggregate"]):
            task_type = TaskType.AGGREGATION
        elif TaskFacet.VISUAL_ELEMENTS in facets and TaskFacet.NUMERIC_METRICS not in facets:
            task_type = TaskType.VISUAL_INSPECTION
        elif TaskFacet.EXACT_IDENTIFIER in facets or TaskFacet.NUMERIC_METRICS in facets:
            task_type = TaskType.LOOKUP
        else:
            task_type = TaskType.SUMMARY

        # 4. Extract validated constraints (hard vs soft vs unresolved)
        hard_constraints: Dict[str, Any] = {}
        soft_preferences: Dict[str, Any] = {}

        if active_document:
            hard_constraints["doc_id"] = active_document

        # Page constraint
        page_m = re.search(r"\bpage\s+([0-9]{1,3})\b", rewritten_query, re.IGNORECASE)
        if page_m:
            hard_constraints["page_number"] = int(page_m.group(1))

        # Doc type preference
        if "certificate" in q_lower or "coa" in q_lower:
            soft_preferences["doc_type"] = "certificate"
        elif "change history" in q_lower or "ecn" in q_lower:
            soft_preferences["doc_type"] = "technical_specification"
        elif "manual" in q_lower:
            soft_preferences["doc_type"] = "manual"

        # Check year ambiguity
        year_m = re.search(r"\b(20[12][0-9])\b", rewritten_query)
        if year_m:
            # A year can be reporting period, filing year, or publication date
            soft_preferences["reporting_period"] = year_m.group(1)

        # 5. Multi-aspect decomposition
        sub_queries: List[SubQueryPlan] = []
        comparison_groups: List[str] = []

        if task_type == TaskType.COMPARISON:
            # Extract revisions or targets
            rev_matches = re.findall(r"rev(?:ision)?\.?\s*([A-Z0-9]+)", rewritten_query, re.IGNORECASE)
            if len(rev_matches) >= 2:
                comparison_groups = [f"Revision {r.upper()}" for r in rev_matches]
                # Extract target metric
                metric_clean = re.sub(r"\b(compare|difference|between|and|rev(?:ision)?\.?\s*[A-Z0-9]+)\b", "", rewritten_query, flags=re.IGNORECASE).strip()
                for idx, rev in enumerate(rev_matches, start=1):
                    sub_queries.append(
                        SubQueryPlan(
                            subquery_id=f"sq_{idx}",
                            query_text=f"What is the {metric_clean} in Revision {rev.upper()}?",
                            target_aspect=f"Revision {rev.upper()} {metric_clean}",
                            hard_constraints={"revision": rev.upper()},
                            dependency_type=DependencyType.PARALLEL,
                        )
                    )
            else:
                # Comparison between two metrics
                comp_m = re.search(r"(?:compare|difference between)\s+(?:the\s+)?(.+?)\s+(?:and|versus|vs\.?)\s+(.+?)(?:\s+(?:for|in)\s+(.+))?$", rewritten_query, re.IGNORECASE)
                if comp_m:
                    m1 = comp_m.group(1).strip()
                    m2 = comp_m.group(2).strip()
                    ctx = f" for {comp_m.group(3).strip()}" if comp_m.group(3) else ""
                    comparison_groups = [m1, m2]
                    sub_queries.append(
                        SubQueryPlan(subquery_id="sq_1", query_text=f"What is {m1}{ctx}?", target_aspect=m1, dependency_type=DependencyType.PARALLEL)
                    )
                    sub_queries.append(
                        SubQueryPlan(subquery_id="sq_2", query_text=f"What is {m2}{ctx}?", target_aspect=m2, dependency_type=DependencyType.PARALLEL)
                    )

        # 6. Build evidence requirements
        req_metrics = []
        for kw in ["operating pressure", "burst pressure", "test pressure", "gamma dose", "endotoxin", "flow rate"]:
            if kw in q_lower:
                req_metrics.append(kw)

        req_units = []
        for kw in ["bar", "kgy", "psi", "eu/ml"]:
            if kw in q_lower:
                req_units.append(kw)

        evidence_reqs = EvidenceRequirements(
            required_metrics=req_metrics,
            required_units=req_units,
            comparison_groups=comparison_groups,
            requires_table_rows=(TaskFacet.NUMERIC_METRICS in facets),
            requires_footnotes=("note" in q_lower or "footnote" in q_lower or "specification" in q_lower),
            requires_visual_crop=(TaskFacet.VISUAL_ELEMENTS in facets),
        )

        # 7. Construct search representations for each retrieval branch
        # Exact lookup identifiers
        exact_lookup_ids = [s.text.strip() for s in protected_spans if s.span_type == "code"]

        # BM25: original text + non-destructive expansions
        bm25_text = cls.expand_vocabulary_non_destructively(rewritten_query)

        # Dense: concise standalone semantic question
        dense_text = re.sub(r"^(please\s+)?(can you\s+)?(tell me\s+)?", "", rewritten_query, flags=re.IGNORECASE).strip()

        # Visual query: natural language description for compatible encoder
        visual_text = f"Visual layout depicting {dense_text}" if TaskFacet.VISUAL_ELEMENTS in facets else dense_text

        search_reps = BranchRepresentations(
            exact_lookup_identifiers=exact_lookup_ids,
            bm25_query=bm25_text,
            dense_query=dense_text,
            visual_query=visual_text,
            structured_filters=hard_constraints,
        )

        completion_cond = "Evidence found for all subquestions" if sub_queries else "Direct evidence retrieved for target query"

        return StructuredQueryPlan(
            original_query=query,
            normalized_query=rewritten_query,
            task_type=task_type,
            facets=facets,
            protected_spans=protected_spans,
            hard_constraints=hard_constraints,
            soft_preferences=soft_preferences,
            unresolved_constraints=unresolved,
            sub_queries=sub_queries,
            evidence_requirements=evidence_reqs,
            completion_condition=completion_cond,
            search_representations=search_reps,
            needs_clarification=is_ambiguous,
            clarification_prompt=f"Please clarify: {'; '.join(unresolved)}" if is_ambiguous else None,
        )

    @classmethod
    def check_evidence_coverage(
        cls,
        plan: StructuredQueryPlan,
        retrieved_evidence_texts: List[str],
    ) -> CoverageReport:
        """
        Verifies evidence completeness against the plan's requirements.
        Triggers bounded retrieval repair if evidence is incomplete.
        """
        missing: List[str] = []
        satisfied: List[str] = []
        combined_text = " ".join(retrieved_evidence_texts).lower()

        # 1. Check comparison groups
        for grp in plan.evidence_requirements.comparison_groups:
            grp_lower = grp.lower()
            if grp_lower in combined_text:
                satisfied.append(grp)
            else:
                missing.append(grp)

        # 2. Check required metrics
        for metric in plan.evidence_requirements.required_metrics:
            if metric.lower() in combined_text:
                satisfied.append(metric)
            else:
                missing.append(metric)

        # 3. Check exact identifiers
        for ident in plan.search_representations.exact_lookup_identifiers:
            if ident.lower() in combined_text:
                satisfied.append(ident)
            else:
                missing.append(f"Identifier {ident}")

        is_complete = len(missing) == 0
        repair_query = None
        repair_branch = None

        if not is_complete:
            # Generate bounded repair query targeting strictly the missing aspect
            missing_focus = missing[0]
            repair_query = f"{plan.normalized_query} specifically focusing on {missing_focus}"
            repair_branch = "exact_lookup" if "Identifier" in missing_focus else "bm25"

        return CoverageReport(
            is_complete=is_complete,
            missing_aspects=missing,
            satisfied_aspects=satisfied,
            repair_query=repair_query,
            repair_branch=repair_branch,
        )
