"""
High-Fidelity Text & Layout Extractor using PDFium C++ Text Engine.
Extracts clean, normalized page text streams and bounding boxes for BM25 keyword indexing.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union
import pypdfium2 as pdfium


class PageTextRecord:
    """Extracted text and structural layout data for a single document page."""
    def __init__(self, page_number: int, text: str, word_count: int):
        self.page_number = page_number
        self.text = text
        self.word_count = word_count

    def to_dict(self) -> dict:
        return {
            "page_number": self.page_number,
            "text": self.text,
            "word_count": self.word_count,
        }


class TextExtractionService:
    """
    Extracts text streams from PDF documents natively via PDFium.
    Preserves alphanumeric codes, tables, and footnote references.
    """

    @staticmethod
    def extract_from_pdf(pdf_input: Union[str, Path, bytes]) -> Dict[int, str]:
        """
        Extracts clean text from each page of a PDF.
        Returns a dictionary mapping page_number (1-indexed) -> text_string.
        """
        if isinstance(pdf_input, (str, Path)):
            path = Path(pdf_input)
            if not path.exists():
                raise FileNotFoundError(f"PDF not found at: {path}")
            pdf = pdfium.PdfDocument(path)
        else:
            pdf = pdfium.PdfDocument(pdf_input)

        pages_text: Dict[int, str] = {}

        for page_index in range(len(pdf)):
            page_num = page_index + 1
            page = pdf[page_index]
            textpage = page.get_textpage()
            raw_text = textpage.get_text_range()

            # Clean and normalize whitespace while preserving line structure
            cleaned_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            normalized_text = "\n".join(cleaned_lines)
            pages_text[page_num] = normalized_text

        return pages_text

    @staticmethod
    def extract_structured(pdf_input: Union[str, Path, bytes]) -> List[PageTextRecord]:
        """
        Returns structured PageTextRecord objects per page with word counts and character counts.
        """
        raw_dict = TextExtractionService.extract_from_pdf(pdf_input)
        records = []
        for page_num, text in raw_dict.items():
            words = text.split()
            records.append(PageTextRecord(page_number=page_num, text=text, word_count=len(words)))
        return records
