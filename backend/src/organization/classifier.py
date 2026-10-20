"""
Hierarchical Multi-Label Classifier (Step 2).
Classifies domain, document type, section role, element type, and quality state separately.
Combines textual evidence, detected structural elements, and layout features.
"""

from typing import List, Set, Tuple
from backend.src.schemas.contracts import (
    DocumentTypeLabel,
    DomainLabel,
    PageMetadata,
    PageQualityAssessment,
    PageType,
    QualityState,
    RegionType,
    SectionRole,
)


class MultiLabelClassifier:
    """
    Classifies documents and sections without forcing everything into a single rigid bucket.
    Supports multi-label assignments and explicit 'unknown' states.
    """

    DOMAIN_KEYWORDS = {
        DomainLabel.FINANCE: ["revenue", "operating income", "ebitda", "balance sheet", "10-k", "cash flow", "fiscal year", "shareholder"],
        DomainLabel.HEALTHCARE: ["pharmaceutical", "cytiva", "gamma", "sterilization", "bio-burden", "endotoxin", "lot", "akta ready", "gxp", "fda"],
        DomainLabel.ENGINEERING: ["specification", "torque", "pressure", "tolerance", "drawing", "schematic", "flow rate", "ecn", "cad"],
        DomainLabel.LEGAL: ["agreement", "jurisdiction", "indemnification", "severability", "clause", "governing law", "confidentiality"],
        DomainLabel.RESEARCH: ["abstract", "introduction", "methodology", "experiment", "doi", "et al.", "conclusion", "references"],
    }

    DOCTYPE_KEYWORDS = {
        DocumentTypeLabel.ANNUAL_REPORT: ["annual report", "form 10-k", "form 10-q", "item 1a", "management discussion"],
        DocumentTypeLabel.CERTIFICATE: ["certificate of analysis", "certificate of conformity", "quality assurance", "release certificate"],
        DocumentTypeLabel.RESEARCH_PAPER: ["abstract", "arxiv", "proceedings of", "ieee", "springer", "elsevier"],
        DocumentTypeLabel.CONTRACT: ["this agreement", "entered into by", "parties hereby agree", "terms and conditions"],
        DocumentTypeLabel.MANUAL: ["user manual", "operating instructions", "installation guide", "standard operating procedure"],
        DocumentTypeLabel.TECHNICAL_SPECIFICATION: ["technical specification", "data sheet", "product specification", "compliance package"],
    }

    SECTION_ROLE_KEYWORDS = {
        SectionRole.ABSTRACT: ["abstract", "executive summary"],
        SectionRole.METHODS: ["methodology", "test method", "experimental procedure", "materials and methods"],
        SectionRole.RESULTS: ["results and discussion", "inspection results", "actual test findings", "acceptance criteria"],
        SectionRole.RISK_FACTORS: ["item 1a", "risk factors", "forward-looking statements"],
        SectionRole.FINANCIAL_STATEMENTS: ["consolidated statements", "balance sheets", "statement of cash flows"],
        SectionRole.SIGNATURES: ["authorized signature", "approved by", "quality assurance release", "sign-off"],
        SectionRole.APPENDIX: ["appendix", "attachment", "exhibit"],
        SectionRole.SPECIFICATIONS: ["specifications", "operating parameters", "acceptance limits"],
    }

    @classmethod
    def classify_domains(cls, text: str) -> List[DomainLabel]:
        """Identifies applicable domains. Can return multiple matching domains."""
        text_lower = text.lower()
        matched = []
        for domain, kws in cls.DOMAIN_KEYWORDS.items():
            if any(kw in text_lower for kw in kws):
                matched.append(domain)
        return matched if matched else [DomainLabel.GENERAL]

    @classmethod
    def classify_document_type(cls, text: str, page_meta: List[PageMetadata]) -> DocumentTypeLabel:
        """Determines primary document type based on text markers and structure."""
        text_lower = text.lower()
        for doc_type, kws in cls.DOCTYPE_KEYWORDS.items():
            if any(kw in text_lower for kw in kws):
                return doc_type

        # Check structural cues
        if any(p.has_stamps or p.has_signatures for p in page_meta):
            return DocumentTypeLabel.CERTIFICATE
        return DocumentTypeLabel.UNKNOWN

    @classmethod
    def classify_section_role(cls, heading_text: str) -> SectionRole:
        """Assigns a functional role to a section heading."""
        h_lower = heading_text.lower()
        for role, kws in cls.SECTION_ROLE_KEYWORDS.items():
            if any(kw in h_lower for kw in kws):
                return role
        return SectionRole.GENERAL

    @classmethod
    def determine_quality_state(cls, quality_assessment: PageQualityAssessment) -> QualityState:
        """Translates technical page assessment into human-interpretable quality state."""
        if quality_assessment.page_type == PageType.DAMAGED:
            return QualityState.DAMAGED
        if not quality_assessment.text_layer_valid:
            return QualityState.PARTIALLY_UNREADABLE
        if quality_assessment.needs_preprocessing:
            return QualityState.NEEDS_REVIEW
        return QualityState.READABLE
