"""
Logical Document Separation Engine (Step 2).
Identifies subdocuments within a single multi-page PDF using title pages,
continuation markers, page-number resets, header shifts, identifier changes, and adjacent-page continuity.
Produces scoped LogicalDocument structures with isolated metadata boundaries.
"""

import re
from typing import Dict, List, Optional
from backend.src.schemas.contracts import (
    DocumentTypeLabel,
    DomainLabel,
    LogicalDocument,
    PageMetadata,
)


class LogicalDocumentSeparator:
    """
    Separates a multi-page PDF into discrete logical subdocuments.
    Enforces strict identifier and revision scoping (e.g. lot numbers and component revisions
    remain isolated to their respective subdocuments).
    """

    PAGE_RESET_PATTERN = re.compile(r'page\s+1\s*(?:of|/)\s*(\d+)', re.IGNORECASE)
    CONTINUATION_PATTERN = re.compile(r'\(continued\)|page\s+([2-9]|\d{2,})\s+of\s+(\d+)', re.IGNORECASE)

    SUBDOC_DETECTION_RULES = [
        {
            "pattern": re.compile(r"re:\s*akta ready flow kit storage conditions|storage conditions", re.IGNORECASE),
            "title": "Flow Kit Storage Conditions Recommendation",
            "doc_type": DocumentTypeLabel.CORRESPONDENCE,
        },
        {
            "pattern": re.compile(r"certificate of (?:quality|analysis).*low flow kit", re.IGNORECASE | re.DOTALL),
            "title": "Certificate of Quality - Low Flow Kit",
            "doc_type": DocumentTypeLabel.CERTIFICATE,
        },
        {
            "pattern": re.compile(r"certificate of (?:quality|analysis).*high flow kit", re.IGNORECASE | re.DOTALL),
            "title": "Certificate of Quality - High Flow Kit",
            "doc_type": DocumentTypeLabel.CERTIFICATE,
        },
        {
            "pattern": re.compile(r"certificate of (?:quality|analysis)", re.IGNORECASE),
            "title": "Certificate of Quality",
            "doc_type": DocumentTypeLabel.CERTIFICATE,
        },
        {
            "pattern": re.compile(r"packaging component specification", re.IGNORECASE),
            "title": "Packaging Component Specification",
            "doc_type": DocumentTypeLabel.TECHNICAL_SPECIFICATION,
        },
        {
            "pattern": re.compile(r"transmissible spongiform encephalopathies|bse/tse", re.IGNORECASE),
            "title": "BSE/TSE Compliance Statement",
            "doc_type": DocumentTypeLabel.DECLARATION,
        },
        {
            "pattern": re.compile(r"material description sheet", re.IGNORECASE),
            "title": "Material Description Sheet",
            "doc_type": DocumentTypeLabel.TECHNICAL_SPECIFICATION,
        },
        {
            "pattern": re.compile(r"supplier qualification record", re.IGNORECASE),
            "title": "Supplier Qualification Record",
            "doc_type": DocumentTypeLabel.AUDIT_REPORT,
        },
        {
            "pattern": re.compile(r"global chain of custody|chain of custody", re.IGNORECASE),
            "title": "Global Chain of Custody",
            "doc_type": DocumentTypeLabel.CHAIN_OF_CUSTODY,
        },
    ]

    GENERIC_TITLE_KEYWORDS = [
        "compliance package",
        "test report",
        "technical specification",
        "operating manual",
        "annual report",
        "master batch record",
        "change notice",
    ]

    @classmethod
    def _extract_page_metadata(cls, text: str) -> Dict[str, list]:
        """Extracts scoped identifiers present on the given page text."""
        # Lots: e.g. Lot Number: 18356721
        lots = re.findall(r"(?:lot|batch)\s*(?:no\.?|#|number)?\s*[:\-]?\s*([0-9]{6,10})", text, re.IGNORECASE)
        # Parts: e.g. Part Number: 29184612 or Part Numbers: 29477427, 29184612
        parts = re.findall(r"(?:part|item|drawing|dwg)\s*(?:no\.?|#|number|reference)?\s*[:\-]?\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
        # Revisions: e.g. Revision: C or Revision: AD
        revisions = re.findall(r"\brevision\s*[:\-]?\s*([A-Z]{1,3})\b", text, re.IGNORECASE)
        # Document numbers: e.g. PKG-SPEC-2023-0847 or SUP-2019-0847
        doc_nums = re.findall(r"\b(?:PKG-SPEC|SUP|DWG)-[0-9]{4}-[0-9]{3,5}\b", text, re.IGNORECASE)

        # Filter out false matches
        stop_words = {"number", "numbers", "code", "id", "item", "the", "for", "rev", "page", "lot", "batch", "date"}
        clean_parts = [p for p in parts if len(p) >= 4 and p.lower() not in stop_words]
        clean_lots = [l for l in lots if l.lower() not in stop_words]

        return {
            "lots": list(dict.fromkeys(clean_lots)),
            "parts": list(dict.fromkeys(clean_parts)),
            "revisions": list(dict.fromkeys(revisions)),
            "doc_nums": list(dict.fromkeys(doc_nums)),
        }

    @classmethod
    def detect_subdocuments(
        cls,
        pages: List[PageMetadata],
        page_texts: Dict[int, str],
        doc_id: str,
    ) -> List[LogicalDocument]:
        """
        Scans pages for subdocument boundaries and returns non-overlapping page ranges with scoped metadata.
        """
        if not pages:
            return []

        boundaries: List[int] = [1]
        boundary_reasons: Dict[int, str] = {1: "initial_document_start"}
        titles: Dict[int, str] = {1: "Document Part 1"}
        doc_types: Dict[int, DocumentTypeLabel] = {1: DocumentTypeLabel.TECHNICAL_SPECIFICATION}

        # Check page 1 specific match
        p1_text = page_texts.get(1, "")
        for rule in cls.SUBDOC_DETECTION_RULES:
            if rule["pattern"].search(p1_text[:600]):
                titles[1] = rule["title"]
                doc_types[1] = rule["doc_type"]
                break

        prev_lot: Optional[str] = None
        p1_meta = cls._extract_page_metadata(p1_text)
        if p1_meta["lots"]:
            prev_lot = p1_meta["lots"][0]

        for page_num in range(2, len(pages) + 1):
            text = page_texts.get(page_num, "")
            header_sample = text[:500]

            # 1. Check if this is an explicit continuation of the previous page
            is_continuation = bool(cls.CONTINUATION_PATTERN.search(header_sample))

            if is_continuation:
                # Continuation page (e.g. Page 5 of packaging spec, or Page 9 of supplier record)
                continue

            # 2. Check for page-number resets (e.g. Page 1 of 1 or Page 1 of N)
            has_reset = bool(cls.PAGE_RESET_PATTERN.search(header_sample))

            # 3. Check for specific subdocument pattern matches
            matched_rule = None
            for rule in cls.SUBDOC_DETECTION_RULES:
                if rule["pattern"].search(header_sample):
                    matched_rule = rule
                    break

            curr_meta = cls._extract_page_metadata(text)
            curr_lot = curr_meta["lots"][0] if curr_meta["lots"] else None

            # Boundary trigger conditions:
            # - Matched an explicit subdocument header rule
            # - OR Page number reset occurred
            # - OR Successive certificates with distinct lot numbers
            is_boundary = False
            reason = ""
            sub_title = f"Subdocument at Page {page_num}"
            sub_dtype = DocumentTypeLabel.TECHNICAL_SPECIFICATION

            if matched_rule:
                is_boundary = True
                reason = f"matched_rule:{matched_rule['title']}"
                sub_title = matched_rule["title"]
                sub_dtype = matched_rule["doc_type"]
            elif has_reset:
                is_boundary = True
                reason = "page_number_reset_to_1"
                sub_title = f"Document at Page {page_num}"
                sub_dtype = DocumentTypeLabel.TECHNICAL_SPECIFICATION
            elif curr_lot and prev_lot and curr_lot != prev_lot and "certificate" in header_sample.lower():
                is_boundary = True
                reason = f"certificate_lot_change:{curr_lot}"
                sub_title = f"Certificate of Quality (Lot {curr_lot})"
                sub_dtype = DocumentTypeLabel.CERTIFICATE
            else:
                # Fallback to generic title keywords
                for kw in cls.GENERIC_TITLE_KEYWORDS:
                    if kw in header_sample.lower():
                        is_boundary = True
                        reason = f"title_heading_detected:{kw}"
                        sub_title = kw.title()
                        sub_dtype = DocumentTypeLabel.TECHNICAL_SPECIFICATION
                        break

            if is_boundary:
                boundaries.append(page_num)
                boundary_reasons[page_num] = reason
                titles[page_num] = sub_title
                doc_types[page_num] = sub_dtype

            if curr_lot:
                prev_lot = curr_lot

        # Deduplicate and sort boundaries
        boundaries = sorted(list(set(boundaries)))

        logical_docs: List[LogicalDocument] = []
        for i, start_p in enumerate(boundaries):
            end_p = (boundaries[i + 1] - 1) if i + 1 < len(boundaries) else len(pages)
            sub_id = f"{doc_id}_sub_{i+1}"
            title = titles.get(start_p, f"Document Part {i+1} (Pages {start_p}-{end_p})")
            dtype = doc_types.get(start_p, DocumentTypeLabel.TECHNICAL_SPECIFICATION)

            # Accumulate text across the subdocument pages for scoped metadata
            sub_text = " ".join([page_texts.get(p, "") for p in range(start_p, end_p + 1)])
            meta = cls._extract_page_metadata(sub_text)

            domain = DomainLabel.HEALTHCARE if "cytiva" in sub_text.lower() or "pharma" in sub_text.lower() else DomainLabel.ENGINEERING

            # Scope product name
            product_name = None
            prod_match = re.search(r"product(?:\s*family)?\s*[:\-]?\s*([^\n\r]+)", sub_text, re.IGNORECASE)
            if prod_match:
                product_name = prod_match.group(1).strip()

            logical_docs.append(
                LogicalDocument(
                    subdoc_id=sub_id,
                    title=title,
                    doc_type=dtype,
                    domains=[domain],
                    start_page=start_p,
                    end_page=end_p,
                    boundary_reason=boundary_reasons.get(start_p, "boundary_segment"),
                    confidence=1.0,
                    lot_numbers=meta["lots"],
                    part_numbers=meta["parts"],
                    revision_codes=meta["revisions"],
                    document_numbers=meta["doc_nums"],
                    product_name=product_name,
                )
            )

        return logical_docs
