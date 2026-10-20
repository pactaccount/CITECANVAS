"""
Visual Coordinate Grounding & Cropping Engine.
Converts normalized 0-1000 bounding boxes to absolute pixel coordinates
and crops visual evidence regions for instant inspection in the UI.
"""

import uuid
from pathlib import Path
from typing import Optional, Tuple, Union
from PIL import Image

from backend.src.schemas.contracts import BoundingBox, VisualCitation


class GroundingEngine:
    """
    Manages coordinate conversions, image cropping, and visual evidence extraction.
    """

    def __init__(self, crop_storage_dir: Optional[Union[str, Path]] = None):
        if crop_storage_dir is None:
            self.crop_storage_dir = Path(__file__).resolve().parent.parent.parent.parent / "storage" / "crops"
        else:
            self.crop_storage_dir = Path(crop_storage_dir)
        self.crop_storage_dir.mkdir(parents=True, exist_ok=True)

    def crop_evidence(
        self,
        page_image_path: Union[str, Path],
        box: BoundingBox,
        doc_id: str,
        page_number: int,
        target_type: str = "table_cell",
        confidence: float = 1.0,
    ) -> VisualCitation:
        """
        Crops the bounding box region from the page image, saves the cropped PNG,
        and returns a fully populated VisualCitation object.
        """
        img_path = Path(page_image_path)
        if not img_path.exists():
            raise FileNotFoundError(f"Page image not found for cropping at: {img_path}")

        with Image.open(img_path) as img:
            width, height = img.size
            px_xmin, px_ymin, px_xmax, px_ymax = box.to_pixel_box(width, height)

            # Clamp coordinates to image boundaries
            px_xmin = max(0, min(px_xmin, width))
            px_ymin = max(0, min(px_ymin, height))
            px_xmax = max(px_xmin + 1, min(px_xmax, width))
            px_ymax = max(px_ymin + 1, min(px_ymax, height))

            # Crop region
            crop_img = img.crop((px_xmin, px_ymin, px_xmax, px_ymax))

            crop_filename = f"{doc_id}_p{page_number}_{uuid.uuid4().hex[:8]}.png"
            crop_filepath = self.crop_storage_dir / crop_filename
            crop_img.save(crop_filepath, format="PNG", optimize=True)

        return VisualCitation(
            page_number=page_number,
            box_2d=box,
            target_type=target_type,
            confidence_score=confidence,
            source_crop_path=str(crop_filepath.relative_to(self.crop_storage_dir.parent.parent)),
        )

    @staticmethod
    def locate_text_span(
        pdf_path: Union[str, Path],
        page_number: int,
        text_query: str,
        padding_y: int = 15,
        padding_x: int = 25,
    ) -> Optional[BoundingBox]:
        """
        Derives an exact normalized 0-1000 bounding box by locating the text span
        inside the native PDF text stream using PDFium C++ search.
        """
        import re
        import pypdfium2 as pdfium

        path = Path(pdf_path)
        if not path.exists():
            return None

        try:
            doc = pdfium.PdfDocument(path)
            if page_number < 1 or page_number > len(doc):
                return None

            page = doc[page_number - 1]
            tp = page.get_textpage()
            w, h = page.get_width(), page.get_height()

            # Attempt full phrase search first
            search = tp.search(text_query)
            match = search.get_next()

            if not match:
                # Fallback: search for prominent keywords / numbers in query
                tokens = re.findall(r'[A-Za-z0-9\-\.\+\>\%]+', text_query)
                for t in sorted(tokens, key=len, reverse=True):
                    if len(t) >= 3 and not t.lower() in ["the", "and", "for", "with", "from"]:
                        s = tp.search(t)
                        m = s.get_next()
                        if m:
                            match = m
                            break

            if not match:
                return None

            char_idx, count = match
            tp.count_rects(char_idx, count)
            rect = tp.get_rect(0)

            xmin = max(0, int((rect[0] / w) * 1000) - padding_x)
            xmax = min(1000, int((rect[2] / w) * 1000) + padding_x)
            ymin = max(0, int(((h - rect[3]) / h) * 1000) - padding_y)
            ymax = min(1000, int(((h - rect[1]) / h) * 1000) + padding_y)

            return BoundingBox(ymin=ymin, xmin=xmin, ymax=ymax, xmax=xmax)
        except Exception:
            return None

