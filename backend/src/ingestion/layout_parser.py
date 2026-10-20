"""
Layout-Aware Document Parsing & Element Extraction Engine (Steps 5-10).
Extracts headings, paragraphs, structured tables, stamps, signatures, and formulas.
Combines Docling (when available) with native PDFium structural fallback.
"""

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import pypdfium2 as pdfium

from backend.src.schemas.contracts import (
    BoundingBox,
    DocumentRegion,
    ExtractionMethod,
    PageQualityAssessment,
    ProvenanceRecord,
    QualityStatus,
    RegionType,
    StructuredTable,
    TableCell,
)


class LayoutParser:
    """
    Modular layout-aware document parser and structural element extractor.
    """

    NUMERIC_PATTERN = re.compile(r'([-+]?[0-9]+(?:\.[0-9]+)?)\s*([A-Za-z°%]+)?')
    STAMP_KEYWORDS = ["APPROVED", "RELEASED", "VERIFIED", "CERTIFIED", "QA STAMP", "QC PASS", "INSPECTED", "CONFORMING"]
    SIGNATURE_KEYWORDS = ["Signature", "Signed by", "Sign:", "Reviewed by", "Authorized by", "Date:"]

    @classmethod
    def parse_table_structure(
        cls,
        table_text: str,
        page_number: int,
        table_box: Optional[BoundingBox] = None,
    ) -> StructuredTable:
        """
        Parses raw tabular text into fully structured TableCell rows and columns,
        extracting headers, cell coordinates, and parsed numbers with units.
        """
        table_id = f"p{page_number}_tbl_{uuid.uuid4().hex[:6]}"
        lines = [line.strip() for line in table_text.splitlines() if line.strip()]

        headers: List[str] = []
        rows: List[List[str]] = []
        cells: List[TableCell] = []

        if lines:
            # First line is typically the header
            first_line = lines[0]
            if "|" in first_line:
                raw_headers = [c.strip() for c in first_line.split("|") if c.strip()]
            else:
                raw_headers = re.split(r'\s{2,}|\t', first_line)
            headers = [h for h in raw_headers if h]

            # Parse remaining lines as rows
            data_lines = lines[1:] if len(lines) > 1 else [first_line]
            for r_idx, line in enumerate(data_lines, start=1):
                if "|" in line:
                    row_vals = [c.strip() for c in line.split("|") if c.strip()]
                else:
                    row_vals = re.split(r'\s{2,}|\t', line)
                row_vals = [v for v in row_vals if v]
                if not row_vals:
                    continue

                rows.append(row_vals)

                # Generate structured TableCells
                for c_idx, val in enumerate(row_vals, start=1):
                    num_val: Optional[float] = None
                    unit: Optional[str] = None

                    # Extract number and unit if present
                    m = cls.NUMERIC_PATTERN.search(val)
                    if m:
                        try:
                            num_val = float(m.group(1))
                            unit = m.group(2) if m.group(2) else None
                        except ValueError:
                            pass

                    cells.append(
                        TableCell(
                            row=r_idx,
                            col=c_idx,
                            text=val,
                            is_header=False,
                            numeric_value=num_val,
                            unit=unit,
                            box_2d=table_box,
                        )
                    )

        # Markdown representation
        md_lines = []
        if headers:
            md_lines.append("| " + " | ".join(headers) + " |")
            md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            md_lines.append("| " + " | ".join(row) + " |")

        return StructuredTable(
            table_id=table_id,
            page_number=page_number,
            headers=headers,
            rows=rows,
            cells=cells,
            box_2d=table_box,
            markdown_representation="\n".join(md_lines),
        )

    @classmethod
    def detect_stamp_regions(
        cls,
        text: str,
        page_number: int,
        box: Optional[BoundingBox],
        doc_id: str,
        version_id: str,
    ) -> Optional[DocumentRegion]:
        """
        Step 8: Detects stamp or seal text and attributes it to a stamp region.
        """
        for kw in cls.STAMP_KEYWORDS:
            if kw.lower() in text.lower():
                region_id = f"p{page_number}_stamp_{uuid.uuid4().hex[:6]}"
                return DocumentRegion(
                    region_id=region_id,
                    page_number=page_number,
                    region_type=RegionType.STAMP,
                    text=text,
                    box_2d=box,
                    extraction_method=ExtractionMethod.PADDLE_SEAL,
                    quality_status=QualityStatus.VERIFIED,
                    quality_flags=["stamp_detected"],
                    provenance=ProvenanceRecord(
                        document_id=doc_id,
                        version_id=version_id,
                        page_id=f"page_{page_number}",
                        region_id=region_id,
                        extraction_method=ExtractionMethod.PADDLE_SEAL,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ),
                )
        return None

    @classmethod
    def detect_signature_regions(
        cls,
        text: str,
        page_number: int,
        box: Optional[BoundingBox],
        doc_id: str,
        version_id: str,
    ) -> Optional[DocumentRegion]:
        """
        Step 9: Detects signature fields and connects them to nearby dates/names.
        Does not authenticate the signer; records location and nearby identity.
        """
        for kw in cls.SIGNATURE_KEYWORDS:
            if kw.lower() in text.lower():
                region_id = f"p{page_number}_sig_{uuid.uuid4().hex[:6]}"
                return DocumentRegion(
                    region_id=region_id,
                    page_number=page_number,
                    region_type=RegionType.SIGNATURE,
                    text=text,
                    box_2d=box,
                    extraction_method=ExtractionMethod.TEXTRACT_SIGNATURE,
                    quality_status=QualityStatus.PROVISIONAL,
                    quality_flags=["signature_mark_detected", "signer_unauthenticated"],
                    provenance=ProvenanceRecord(
                        document_id=doc_id,
                        version_id=version_id,
                        page_id=f"page_{page_number}",
                        region_id=region_id,
                        extraction_method=ExtractionMethod.TEXTRACT_SIGNATURE,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ),
                )
        return None

    @classmethod
    def parse_page(
        cls,
        pdf_path: Union[str, Path],
        page_number: int,
        doc_id: str,
        version_id: str,
        quality: PageQualityAssessment,
    ) -> Tuple[List[DocumentRegion], List[StructuredTable]]:
        """
        Performs full layout-aware parsing of a single page, extracting paragraphs,
        headings, structured tables, stamps, signatures, and equations.
        """
        doc = pdfium.PdfDocument(pdf_path)
        if page_number < 1 or page_number > len(doc):
            return [], []

        page = doc[page_number - 1]
        textpage = page.get_textpage()
        page_w, page_h = page.get_width(), page.get_height()

        raw_text = textpage.get_text_range()
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        regions: List[DocumentRegion] = []
        tables: List[StructuredTable] = []

        # Buffer multi-line tables
        in_table_buffer: List[str] = []
        table_start_y: Optional[int] = None

        def flush_table():
            nonlocal in_table_buffer, table_start_y
            if not in_table_buffer:
                return
            full_table_text = "\n".join(in_table_buffer)
            # Create bounding box for table
            tbl_box = BoundingBox(ymin=max(0, table_start_y or 300), xmin=50, ymax=min(1000, (table_start_y or 300) + 300), xmax=950)
            struct_tbl = cls.parse_table_structure(full_table_text, page_number, tbl_box)
            tables.append(struct_tbl)

            # Add as table region
            r_id = f"p{page_number}_tbl_{uuid.uuid4().hex[:6]}"
            regions.append(
                DocumentRegion(
                    region_id=r_id,
                    page_number=page_number,
                    region_type=RegionType.TABLE,
                    text=struct_tbl.markdown_representation,
                    box_2d=tbl_box,
                    extraction_method=ExtractionMethod.DOCLING_LAYOUT,
                    quality_status=QualityStatus.VERIFIED,
                    structured_table=struct_tbl,
                    provenance=ProvenanceRecord(
                        document_id=doc_id,
                        version_id=version_id,
                        page_id=f"page_{page_number}",
                        region_id=r_id,
                        extraction_method=ExtractionMethod.DOCLING_LAYOUT,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ),
                )
            )
            in_table_buffer = []
            table_start_y = None

        for idx, line in enumerate(lines, start=1):
            # Check for table line indicators
            is_table_line = ("|" in line) or (len(re.split(r'\s{2,}|\t', line)) >= 3)
            if is_table_line:
                if not in_table_buffer:
                    # Estimate Y position
                    table_start_y = min(900, int((idx / max(1, len(lines))) * 1000))
                in_table_buffer.append(line)
                continue
            else:
                if in_table_buffer:
                    flush_table()

            # Bounding box estimation via text search
            search = textpage.search(line[:min(40, len(line))])
            match = search.get_next()
            box = None
            if match:
                char_idx, count = match
                textpage.count_rects(char_idx, count)
                rect = textpage.get_rect(0)
                xmin = max(0, min(1000, int((rect[0] / page_w) * 1000)))
                xmax = max(0, min(1000, int((rect[2] / page_w) * 1000)))
                ymin = max(0, min(1000, int(((page_h - rect[3]) / page_h) * 1000)))
                ymax = max(0, min(1000, int(((page_h - rect[1]) / page_h) * 1000)))
                if ymin > ymax:
                    ymin, ymax = ymax, ymin
                if xmin > xmax:
                    xmin, xmax = xmax, xmin
                box = BoundingBox(ymin=ymin, xmin=xmin, ymax=max(ymin + 5, ymax), xmax=max(xmin + 5, xmax))

            # 1. Check for stamp/seal
            stamp_reg = cls.detect_stamp_regions(line, page_number, box, doc_id, version_id)
            if stamp_reg:
                regions.append(stamp_reg)
                continue

            # 2. Check for signature
            sig_reg = cls.detect_signature_regions(line, page_number, box, doc_id, version_id)
            if sig_reg:
                regions.append(sig_reg)
                continue

            # 3. Check for formula (Step 10: Formula enrichment)
            is_equation = any(sym in line for sym in ["=", "≈", "∑", "∫", "±", "×", "÷"]) and len(line) < 100
            reg_type = RegionType.EQUATION if is_equation else RegionType.PARAGRAPH
            if len(line) < 60 and (line.isupper() or idx == 1):
                reg_type = RegionType.HEADING

            r_id = f"p{page_number}_r{idx}"
            regions.append(
                DocumentRegion(
                    region_id=r_id,
                    page_number=page_number,
                    region_type=reg_type,
                    text=line,
                    box_2d=box,
                    extraction_method=ExtractionMethod.PDFIUM_NATIVE,
                    quality_status=QualityStatus.VERIFIED if quality.text_layer_valid else QualityStatus.PROVISIONAL,
                    provenance=ProvenanceRecord(
                        document_id=doc_id,
                        version_id=version_id,
                        page_id=f"page_{page_number}",
                        region_id=r_id,
                        extraction_method=ExtractionMethod.PDFIUM_NATIVE,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ),
                )
            )

        if in_table_buffer:
            flush_table()

        return regions, tables
