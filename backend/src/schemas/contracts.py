"""
EvidenceDesk Core Data Contracts & Schemas
Enterprise-grade Pydantic v2 data models for grounded document QA.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator, model_validator


class CitationStatus(str, Enum):
    """Citation status reflecting factual verification."""
    DIRECT = "direct"                 # Explicitly confirmed by visual evidence
    INDIRECT = "indirect"             # Inferred from surrounding context
    ABSTAIN = "abstain"               # Information is missing / unanswerable (refusal to hallucinate)
    UNSUPPORTED = "unsupported"       # Claim is contradicted by visual evidence
    CONTRADICTORY = "contradictory"   # Conflicting evidence present in document


class DomainLabel(str, Enum):
    """Multi-label domain categorization."""
    FINANCE = "finance"
    RESEARCH = "research"
    HEALTHCARE = "healthcare"
    ENGINEERING = "engineering"
    LEGAL = "legal"
    GENERAL = "general"
    UNKNOWN = "unknown"


class DocumentTypeLabel(str, Enum):
    """Hierarchical document type classification."""
    ANNUAL_REPORT = "annual_report"
    RESEARCH_PAPER = "research_paper"
    CONTRACT = "contract"
    CERTIFICATE = "certificate"
    MANUAL = "manual"
    CORRESPONDENCE = "correspondence"
    TECHNICAL_SPECIFICATION = "technical_specification"
    CHAIN_OF_CUSTODY = "chain_of_custody"
    DECLARATION = "declaration"
    AUDIT_REPORT = "audit_report"
    UNKNOWN = "unknown"


class SectionRole(str, Enum):
    """Functional role of a section inside a logical document."""
    ABSTRACT = "abstract"
    METHODS = "methods"
    RESULTS = "results"
    RISK_FACTORS = "risk_factors"
    FINANCIAL_STATEMENTS = "financial_statements"
    SIGNATURES = "signatures"
    APPENDIX = "appendix"
    OVERVIEW = "overview"
    SPECIFICATIONS = "specifications"
    GENERAL = "general"


class QualityState(str, Enum):
    """Quality state of a document, page, or element."""
    READABLE = "readable"
    PARTIALLY_UNREADABLE = "partially_unreadable"
    DAMAGED = "damaged"
    EXTRACTION_FAILED = "extraction_failed"
    NEEDS_REVIEW = "needs_review"


class ContentRelationType(str, Enum):
    """Typed relationship connecting cross-page or cross-element components."""
    TABLE_CONTINUATION = "table_continuation"
    CAPTION_FOR = "caption_for"
    FOOTNOTE_FOR = "footnote_for"
    REFERENCES_FIGURE = "references_figure"
    REFERENCES_EQUATION = "references_equation"
    PARENT_CHILD = "parent_child"
    SUPERSEDES = "supersedes"
    AMENDS = "amends"


class PageType(str, Enum):
    """Page classification based on text layer and visual characteristics."""
    DIGITAL = "digital"               # Clean embedded vector text layer
    SCANNED = "scanned"               # Pure bitmap scan, no text layer
    MIXED = "mixed"                   # Digital text with embedded raster scan regions
    DAMAGED = "damaged"               # Skewed, torn, blurred, or degraded scan


class RegionType(str, Enum):
    """Structural region classification within a document page."""
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    TABLE = "table"
    TABLE_ROW_GROUP = "table_row_group"
    FIGURE = "figure"
    CHART = "chart"
    STAMP = "stamp"
    SIGNATURE = "signature"
    EQUATION = "equation"
    FOOTNOTE = "footnote"


class ExtractionMethod(str, Enum):
    """Provenance method used to extract the region."""
    PDFIUM_NATIVE = "pdfium_native"
    DOCLING_LAYOUT = "docling_layout"
    RAPID_OCR = "rapid_ocr"
    PADDLE_SEAL = "paddle_seal"
    TEXTRACT_SIGNATURE = "textract_signature"
    VLM_PROPOSAL = "vlm_proposal"
    HEURISTIC_LAYOUT = "heuristic_layout"


class QualityStatus(str, Enum):
    """Status indicating certainty of extraction."""
    VERIFIED = "verified"
    PROVISIONAL = "provisional"
    UNCERTAIN = "uncertain"
    DAMAGED = "damaged"
    UNRESOLVED = "unresolved"


class FloatBoundingBox(BaseModel):
    """
    Exact floating-point coordinates preserving physical page dimensions,
    rotation, and sub-pixel geometries without rounding loss.
    """
    ymin_pt: float = Field(description="Top edge in points")
    xmin_pt: float = Field(description="Left edge in points")
    ymax_pt: float = Field(description="Bottom edge in points")
    xmax_pt: float = Field(description="Right edge in points")
    page_width_pt: float = Field(default=595.0, description="Page width in points")
    page_height_pt: float = Field(default=842.0, description="Page height in points")
    rotation_deg: int = Field(default=0, description="Page rotation in degrees (0, 90, 180, 270)")

    def to_normalized_box(self) -> "BoundingBox":
        """Converts exact float points to normalized 0-1000 integer box for standard visualization."""
        w = max(1.0, self.page_width_pt)
        h = max(1.0, self.page_height_pt)
        return BoundingBox(
            ymin=max(0, min(1000, int((self.ymin_pt / h) * 1000))),
            xmin=max(0, min(1000, int((self.xmin_pt / w) * 1000))),
            ymax=max(0, min(1000, int((self.ymax_pt / h) * 1000))),
            xmax=max(0, min(1000, int((self.xmax_pt / w) * 1000))),
        )



class BoundingBox(BaseModel):
    """
    Normalized 0-1000 coordinate bounding box on a document page image.
    0 = top/left edge (0%), 1000 = bottom/right edge (100%).
    """
    ymin: int = Field(ge=0, le=1000, description="Start from top edge (0-1000)")
    xmin: int = Field(ge=0, le=1000, description="Start from left edge (0-1000)")
    ymax: int = Field(ge=0, le=1000, description="End at bottom edge (0-1000)")
    xmax: int = Field(ge=0, le=1000, description="End at right edge (0-1000)")

    @model_validator(mode="after")
    def validate_coordinates(self) -> "BoundingBox":
        if self.ymin > self.ymax:
            raise ValueError(f"ymin ({self.ymin}) cannot be greater than ymax ({self.ymax})")
        if self.xmin > self.xmax:
            raise ValueError(f"xmin ({self.xmin}) cannot be greater than xmax ({self.xmax})")
        return self

    def to_pixel_box(self, image_width: int, image_height: int) -> Tuple[int, int, int, int]:
        """Convert normalized (0-1000) coordinates to absolute pixel box (xmin, ymin, xmax, ymax)."""
        px_xmin = int((self.xmin / 1000.0) * image_width)
        px_ymin = int((self.ymin / 1000.0) * image_height)
        px_xmax = int((self.xmax / 1000.0) * image_width)
        px_ymax = int((self.ymax / 1000.0) * image_height)
        return (px_xmin, px_ymin, px_xmax, px_ymax)

    def iou(self, other: "BoundingBox") -> float:
        """Calculate Intersection over Union (IoU) with another bounding box."""
        inter_ymin = max(self.ymin, other.ymin)
        inter_xmin = max(self.xmin, other.xmin)
        inter_ymax = min(self.ymax, other.ymax)
        inter_xmax = min(self.xmax, other.xmax)

        inter_w = max(0, inter_xmax - inter_xmin)
        inter_h = max(0, inter_ymax - inter_ymin)
        inter_area = inter_w * inter_h

        self_area = (self.xmax - self.xmin) * (self.ymax - self.ymin)
        other_area = (other.xmax - other.xmin) * (other.ymax - other.ymin)
        union_area = self_area + other_area - inter_area

        if union_area <= 0:
            return 0.0
        return inter_area / union_area


class ProvenanceRecord(BaseModel):
    """Audit provenance tracking how a document element was created."""
    document_id: str
    version_id: str
    page_id: str
    region_id: str
    extraction_method: ExtractionMethod
    model_version: str = "v3.0-hybrid"
    confidence: float = 1.0
    timestamp: str


class TableCell(BaseModel):
    """Structured table cell representation for precise calculations."""
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    text: str
    is_header: bool = False
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    box_2d: Optional[BoundingBox] = None


class StructuredTable(BaseModel):
    """Complete structured table with cell hierarchy and coordinates."""
    table_id: str
    page_number: int
    caption: Optional[str] = None
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    cells: List[TableCell] = Field(default_factory=list)
    box_2d: Optional[BoundingBox] = None
    continued_from_page: Optional[int] = None
    continues_on_page: Optional[int] = None
    markdown_representation: str = ""


class DocumentRegion(BaseModel):
    """
    Fine-grained structural region within a document page.
    Shared identifier: document_id -> version_id -> page_id -> region_id
    Maintains clean separation between source content and search representations.
    """
    region_id: str
    parent_section_id: Optional[str] = None
    page_number: int
    region_type: RegionType
    text: str = Field(description="Legacy/Primary text representation")
    source_text: str = Field(default="", description="Extracted/transcribed content with source-span mapping")
    search_text: str = Field(default="", description="Heading/context prefix plus content used for embedding")
    generated_context: Optional[str] = Field(default=None, description="Optional explanatory text, explicitly labeled as generated")
    token_count: int = Field(default=0, description="Measured token count of search_text")
    box_2d: Optional[BoundingBox] = None
    float_box: Optional[FloatBoundingBox] = None
    extraction_method: ExtractionMethod = ExtractionMethod.PDFIUM_NATIVE
    quality_status: QualityStatus = QualityStatus.VERIFIED
    quality_flags: List[str] = Field(default_factory=list)
    structured_table: Optional[StructuredTable] = None
    provenance: Optional[ProvenanceRecord] = None
    source_crop_path: Optional[str] = None
    identifiers: List[str] = Field(default_factory=list, description="Extracted lot numbers, ECNs, part numbers")
    local_identifiers: List[str] = Field(default_factory=list, description="Locally scoped identifiers for this chunk only")
    relations: List[str] = Field(default_factory=list, description="IDs of linked parent, footnotes, captions, continuations")

    @model_validator(mode="after")
    def sync_texts(self) -> "DocumentRegion":
        if not self.source_text and self.text:
            self.source_text = self.text
        if not self.search_text and self.text:
            self.search_text = self.text
        if not self.text and self.source_text:
            self.text = self.source_text
        return self


class PageQualityAssessment(BaseModel):
    """Detailed quality assessment of a single document page."""
    page_number: int
    page_type: PageType
    text_layer_valid: bool
    character_count: int
    word_count: int
    blur_score: float = 100.0          # Laplacian variance
    contrast_score: float = 1.0        # RMS contrast
    skew_angle_deg: float = 0.0        # Detected skew in degrees
    needs_preprocessing: bool = False
    needs_ocr: bool = False
    quality_flags: List[str] = Field(default_factory=list)


class ProcessingVersion(BaseModel):
    """Record of pipeline processing configuration and versioning."""
    version_id: str
    document_id: str
    pipeline_version: str = "v3.0-hybrid"
    primary_parser: str = "docling_with_pdfium_fallback"
    ocr_engine: str = "rapid_ocr_paddle_fallback"
    embedding_model: str = "bge-m3"
    visual_model: str = "colpali-qdrant"
    created_at: str


class VisualCitation(BaseModel):
    """Citation pointing to exact visual region on a specific document page."""
    document_version: Optional[str] = None
    page_number: int = Field(ge=1, description="1-indexed page number in the document")
    region_id: Optional[str] = None
    box_2d: Optional[BoundingBox] = Field(default=None, description="Normalized bounding box of evidence")
    target_type: str = Field(
        default="table_cell",
        description="Type of visual evidence: table_cell | chart | diagram | footnote | text_passage | stamp | signature"
    )
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Model confidence in grounding")
    quality_status: QualityStatus = QualityStatus.VERIFIED
    source_crop_path: Optional[str] = Field(default=None, description="Path to cropped image snippet")


class GroundedAnswer(BaseModel):
    """
    Standard output payload for EvidenceDesk.
    Contains verified answer, normalized numbers, visual citation, and abstention status.
    """
    query: str = Field(description="The original user query")
    status: CitationStatus = Field(description="direct, abstain, unsupported, or contradictory")
    answer: Optional[str] = Field(default=None, description="Natural language answer text")
    numeric_value: Optional[float] = Field(default=None, description="Extracted numerical metric value")
    range_value: Optional[Tuple[float, float]] = Field(default=None, description="Extracted numerical range (lower, upper)")
    financial_amount: Optional[Dict[str, Any]] = Field(default=None, description="Extracted financial amount with currency and scale")
    unit: Optional[str] = Field(default=None, description="Normalized unit (e.g. USD, USD Millions, psi, MWh, kGy)")
    citation: Optional[VisualCitation] = Field(default=None, description="Supporting visual evidence")
    claim_citations: List[str] = Field(default_factory=list, description="Claim-level evidence citations [EVID-1, EVID-2]")
    calculation_record: Optional[Any] = Field(default=None, description="Deterministic calculation audit record")
    outcome_type: str = Field(default="complete", description="complete | partial | insufficient_evidence | conflicting_evidence | ambiguous")
    abstention_reason: Optional[str] = Field(default=None, description="Explanation if status is abstain")
    latency_ms: float = Field(default=0.0, description="Total pipeline latency in milliseconds")
    model_id: str = Field(default="llama-3.2-11b-vision", description="Model identifier used for inference")

    @model_validator(mode="after")
    def validate_abstention(self) -> "GroundedAnswer":
        if self.status == CitationStatus.ABSTAIN:
            if not self.abstention_reason:
                raise ValueError("abstention_reason is required when status is 'abstain'")
        elif self.status == CitationStatus.DIRECT:
            if not self.answer and self.numeric_value is None:
                raise ValueError("answer or numeric_value is required when status is 'direct'")
        return self


class PageMetadata(BaseModel):
    """Metadata describing a rendered document page."""
    page_number: int = Field(ge=1)
    image_path: str = Field(description="Relative path to 300 DPI rendered PNG")
    retrieval_image_path: Optional[str] = Field(default=None, description="Path to retrieval-scale image (e.g., 1400px)")
    width: int = Field(description="Image width in pixels")
    height: int = Field(description="Image height in pixels")
    quality: Optional[PageQualityAssessment] = None
    has_tables: bool = Field(default=False)
    has_charts: bool = Field(default=False)
    has_stamps: bool = Field(default=False)
    has_signatures: bool = Field(default=False)
    regions_count: int = Field(default=0)


class ContentRelationship(BaseModel):
    """Explicit cross-page or cross-element relationship link."""
    source_id: str
    target_id: str
    relation_type: ContentRelationType
    confidence: float = 1.0
    description: Optional[str] = None


class LogicalSection(BaseModel):
    """Reconstructed section in the logical document hierarchy."""
    section_id: str
    logical_doc_id: str
    title: str
    heading_level: int = 1
    heading_path: str = ""
    parent_section_id: Optional[str] = None
    element_ids: List[str] = Field(default_factory=list)


class LogicalDocument(BaseModel):
    """
    Subdocument boundary representation within a multi-part PDF.
    Enables logical document separation without mutating the original PDF.
    """
    subdoc_id: str
    title: str
    doc_type: DocumentTypeLabel = DocumentTypeLabel.UNKNOWN
    domains: List[DomainLabel] = Field(default_factory=lambda: [DomainLabel.GENERAL])
    start_page: int
    end_page: int
    boundary_reason: str = "detected_title_page_or_header_shift"
    confidence: float = 1.0
    lot_numbers: List[str] = Field(default_factory=list)
    part_numbers: List[str] = Field(default_factory=list)
    revision_codes: List[str] = Field(default_factory=list)
    document_numbers: List[str] = Field(default_factory=list)
    product_name: Optional[str] = None
    scoped_metadata: Dict[str, Any] = Field(default_factory=dict)


class TemporalRecord(BaseModel):
    """Temporal and version organization metadata."""
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    reporting_period: Optional[str] = None
    filing_date: Optional[str] = None
    ingestion_timestamp: str


class DomainExtension(BaseModel):
    """Domain-specific structured extension fields."""
    financial: Optional[dict] = None
    technical_pharma: Optional[dict] = None
    research: Optional[dict] = None


class ExtractedFieldRecord(BaseModel):
    """Structured field extraction with provenance and validation status."""
    field_name: str
    raw_value: str
    normalized_value: Optional[str] = None
    source_region_id: str
    page_number: int
    extraction_method: ExtractionMethod
    validation_status: QualityStatus = QualityStatus.VERIFIED
    uncertainty: float = 0.0


class FacetedCatalogRecord(BaseModel):
    """Faceted catalog attributes for filtering and search indexing."""
    document_id: str
    version_id: str
    title: str
    domains: List[str] = Field(default_factory=list)
    document_types: List[str] = Field(default_factory=list)
    organizations: List[str] = Field(default_factory=list)
    identifiers: List[str] = Field(default_factory=list)
    effective_date: Optional[str] = None
    quality_state: QualityState = QualityState.READABLE


class StructuredDocument(BaseModel):
    """
    Complete structured document representation (JSONB / PostgreSQL).
    Represents original evidence, sections, regions, tables, and quality flags.
    """
    document_id: str
    version_id: str
    filename: str
    sha256_hash: str
    total_pages: int
    processing_version: ProcessingVersion
    pages: List[PageMetadata] = Field(default_factory=list)
    logical_documents: List[LogicalDocument] = Field(default_factory=list)
    sections: List[LogicalSection] = Field(default_factory=list)
    regions: List[DocumentRegion] = Field(default_factory=list)
    tables: List[StructuredTable] = Field(default_factory=list)
    relationships: List[ContentRelationship] = Field(default_factory=list)
    extracted_fields: List[ExtractedFieldRecord] = Field(default_factory=list)
    temporal_record: Optional[TemporalRecord] = None
    domain_extension: Optional[DomainExtension] = None
    faceted_catalog: Optional[FacetedCatalogRecord] = None
    quality_flags: List[str] = Field(default_factory=list)


class DocumentCase(BaseModel):
    """Case representation for an uploaded, rendered, and indexed document."""
    doc_id: str = Field(description="Deterministic SHA-256 hash of PDF binary")
    filename: str = Field(description="Original filename")
    total_pages: int = Field(ge=1)
    uploaded_at: str = Field(description="ISO-8601 timestamp")
    pages: List[PageMetadata] = Field(default_factory=list)
    structured_doc: Optional[StructuredDocument] = None


class ExpandedEvidence(BaseModel):
    """
    Expanded evidence payload for generation/answering.
    Distinguishes what was retrieved to locate the answer from the surrounding
    evidence context provided to the model.
    """
    chunk_id: str
    region_type: RegionType
    page_number: int
    core_text: str
    expanded_text: str
    token_count: int
    parent_section: Optional[str] = None
    linked_table: Optional[StructuredTable] = None
    linked_footnotes: List[str] = Field(default_factory=list)
    linked_image_crop_path: Optional[str] = None
    box_2d: Optional[BoundingBox] = None
    relations: List[str] = Field(default_factory=list)
    is_truncated: bool = False


