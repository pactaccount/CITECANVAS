"""
Page-Level Quality & Text-Layer Assessment Module (Step 2).
Inspects PDFium text layer and visual characteristics.
Routes digital, scanned, mixed, and damaged pages differently within the same PDF.
"""

import math
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from PIL import Image
import pypdfium2 as pdfium

from backend.src.schemas.contracts import PageQualityAssessment, PageType


class QualityAssessor:
    """
    Assesses page quality, text layer validity, contrast, and blur metrics.
    """

    @staticmethod
    def calculate_laplacian_variance(image_path: Union[str, Path]) -> float:
        """
        Calculates sharpness/blur score using 2D discrete Laplacian filter approximation.
        Higher score = sharper image. Score < 30 indicates significant blur.
        """
        with Image.open(image_path).convert("L") as img:
            # Resize for fast metric computation
            small = img.resize((512, 512), Image.Resampling.BILINEAR)
            arr = np.array(small, dtype=np.float32)

            # 3x3 Laplacian kernel
            # [ 0,  1,  0]
            # [ 1, -4,  1]
            # [ 0,  1,  0]
            lap = (
                arr[:-2, 1:-1]
                + arr[2:, 1:-1]
                + arr[1:-1, :-2]
                + arr[1:-1, 2:]
                - 4.0 * arr[1:-1, 1:-1]
            )
            return float(np.var(lap))

    @staticmethod
    def calculate_contrast(image_path: Union[str, Path]) -> float:
        """Calculates normalized RMS contrast of image."""
        with Image.open(image_path).convert("L") as img:
            small = img.resize((256, 256), Image.Resampling.BILINEAR)
            arr = np.array(small, dtype=np.float32) / 255.0
            return float(np.std(arr))

    @staticmethod
    def check_text_entropy(text: str) -> float:
        """
        Calculates Shannon entropy of character distribution.
        Values between 3.5 and 5.0 typically indicate natural language text.
        Extremely low or high entropy indicates corrupted text layers.
        """
        if not text:
            return 0.0
        counts: Dict[str, int] = {}
        for c in text:
            counts[c] = counts.get(c, 0) + 1
        n = len(text)
        entropy = -sum((cnt / n) * math.log2(cnt / n) for cnt in counts.values())
        return entropy

    @classmethod
    def assess_page(
        cls,
        pdf_path: Union[str, Path],
        page_number: int,
        page_image_path: Union[str, Path],
    ) -> PageQualityAssessment:
        """
        Assesses a single document page and determines routing requirements.
        """
        doc = pdfium.PdfDocument(pdf_path)
        if page_number < 1 or page_number > len(doc):
            raise IndexError(f"Page {page_number} out of range (1..{len(doc)})")

        page = doc[page_number - 1]
        textpage = page.get_textpage()
        text = textpage.get_text_range()

        char_count = len(text.strip())
        word_count = len(text.split())
        entropy = cls.check_text_entropy(text)

        blur_score = cls.calculate_laplacian_variance(page_image_path)
        contrast_score = cls.calculate_contrast(page_image_path)

        quality_flags = []
        text_layer_valid = True

        # Check text layer reliability
        if char_count < 25:
            text_layer_valid = False
            quality_flags.append("sparse_or_empty_text_layer")
        elif entropy < 2.5 or entropy > 6.0:
            text_layer_valid = False
            quality_flags.append("abnormal_character_entropy")

        # Classify PageType
        if not text_layer_valid and blur_score < 25.0:
            page_type = PageType.DAMAGED
            quality_flags.append("severe_blur_detected")
        elif not text_layer_valid:
            page_type = PageType.SCANNED
            quality_flags.append("scanned_bitmap_page")
        elif char_count > 150:
            page_type = PageType.DIGITAL
        else:
            page_type = PageType.MIXED
            quality_flags.append("mixed_text_and_graphics")

        needs_ocr = not text_layer_valid or page_type in (PageType.SCANNED, PageType.DAMAGED)
        needs_preprocessing = blur_score < 40.0 or contrast_score < 0.15

        return PageQualityAssessment(
            page_number=page_number,
            page_type=page_type,
            text_layer_valid=text_layer_valid,
            character_count=char_count,
            word_count=word_count,
            blur_score=round(blur_score, 2),
            contrast_score=round(contrast_score, 3),
            skew_angle_deg=0.0,
            needs_preprocessing=needs_preprocessing,
            needs_ocr=needs_ocr,
            quality_flags=quality_flags,
        )
