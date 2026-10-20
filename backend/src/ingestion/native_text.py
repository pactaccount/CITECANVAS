"""
Native Text Extraction with Coordinates & Reconciled Layer Validation (Step 3).
Uses PDFium to extract embedded glyphs and word bounding boxes without unnecessary OCR.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import pypdfium2 as pdfium

from backend.src.schemas.contracts import (
    BoundingBox,
    DocumentRegion,
    ExtractionMethod,
    QualityStatus,
    RegionType,
)


class NativeTextExtractor:
    """
    Extracts high-fidelity text streams with normalized 0-1000 bounding boxes
    directly from PDF vector layers.
    """

    IDENTIFIER_PATTERNS = [
        r'\b(?:Lot|LOT|Batch|BATCH)[\s#:]*([A-Za-z0-9\-]+)\b',
        r'\b(?:ECN|ecn)[\s\-:]*([A-Za-z0-9\-]+)\b',
        r'\b(?:Item|ITEM|Part|PART|REF|Ref)[\s#:]*([A-Za-z0-9\-]+)\b',
        r'\b(?:Doc|DOC|Specification|Spec)[\s#:]*([A-Za-z0-9\-]+)\b',
        r'([0-9]+\.?[0-9]*\s*(?:kGy|psi|bar|rpm|mL|mg|°C|%))\b',
    ]

    @classmethod
    def extract_identifiers(cls, text: str) -> List[str]:
        """Extracts critical enterprise identifiers (Lot numbers, ECNs, specs)."""
        found = set()
        for pat in cls.IDENTIFIER_PATTERNS:
            matches = re.findall(pat, text, re.IGNORECASE)
            for m in matches:
                clean = m.strip() if isinstance(m, str) else m[0].strip()
                if len(clean) >= 2:
                    found.add(clean)
        return sorted(list(found))

    @classmethod
    def extract_page_regions(
        cls,
        pdf_path: Union[str, Path],
        page_number: int,
        doc_id: str,
        version_id: str,
        text_layer_valid: bool = True,
    ) -> List[DocumentRegion]:
        """
        Extracts structural text blocks and lines with normalized bounding boxes.
        """
        doc = pdfium.PdfDocument(pdf_path)
        if page_number < 1 or page_number > len(doc):
            raise IndexError(f"Page {page_number} out of range")

        page = doc[page_number - 1]
        textpage = page.get_textpage()
        page_w, page_h = page.get_width(), page.get_height()

        regions: List[DocumentRegion] = []
        raw_text = textpage.get_text_range()

        # Split into semantic lines / paragraphs
        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [line.strip() for line in raw_text.splitlines() if line.strip()]

        for idx, para in enumerate(paragraphs, start=1):
            region_id = f"p{page_number}_r{idx}"

            # Search textpage for bounding box of this paragraph
            box = None
            search = textpage.search(para[:min(50, len(para))])
            match = search.get_next()
            if match:
                char_idx, count = match
                textpage.count_rects(char_idx, count)
                rect = textpage.get_rect(0)
                # Convert PDF bottom-left to top-left 0-1000
                xmin = max(0, min(1000, int((rect[0] / page_w) * 1000)))
                xmax = max(0, min(1000, int((rect[2] / page_w) * 1000)))
                ymin = max(0, min(1000, int(((page_h - rect[3]) / page_h) * 1000)))
                ymax = max(0, min(1000, int(((page_h - rect[1]) / page_h) * 1000)))

                # Ensure box validity
                if ymin > ymax:
                    ymin, ymax = ymax, ymin
                if xmin > xmax:
                    xmin, xmax = xmax, xmin
                box = BoundingBox(ymin=ymin, xmin=xmin, ymax=max(ymin + 5, ymax), xmax=max(xmin + 5, xmax))

            # Classify region type
            region_type = RegionType.PARAGRAPH
            if len(para) < 60 and (para.isupper() or idx == 1):
                region_type = RegionType.HEADING
            elif any(sym in para for sym in ["|", "  ", "\t"]) and "\n" in para:
                region_type = RegionType.TABLE

            quality_status = QualityStatus.VERIFIED if text_layer_valid else QualityStatus.PROVISIONAL
            identifiers = cls.extract_identifiers(para)

            regions.append(
                DocumentRegion(
                    region_id=region_id,
                    page_number=page_number,
                    region_type=region_type,
                    text=para,
                    box_2d=box,
                    extraction_method=ExtractionMethod.PDFIUM_NATIVE,
                    quality_status=quality_status,
                    identifiers=identifiers,
                )
            )

        return regions
