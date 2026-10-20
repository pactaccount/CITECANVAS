"""
High-Speed Document Ingestion & 300 DPI Rendering Service.
Converts PDFs and standalone images into normalized, high-resolution 300 DPI page images
with SHA-256 cryptographic deduplication and caching.
"""

import hashlib
import os
from pathlib import Path
from typing import Union, List, Optional
from PIL import Image
import pypdfium2 as pdfium

from backend.src.schemas.contracts import DocumentCase, PageMetadata


# Standard PDF scale factor: 72 points per inch -> 300 DPI print quality
SCALE_300_DPI = 300.0 / 72.0  # ≈ 4.1667


class DocumentIngestionService:
    """
    Ingests PDF documents or standalone images, renders them to 300 DPI PNGs,
    and caches them deterministically by binary hash.
    """

    def __init__(self, storage_dir: Optional[Union[str, Path]] = None):
        if storage_dir is None:
            self.storage_dir = Path(__file__).resolve().parent.parent.parent.parent / "storage" / "pages"
        else:
            self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        """Compute deterministic SHA-256 hexadecimal hash from raw binary data."""
        return hashlib.sha256(data).hexdigest()

    def ingest_pdf(self, pdf_input: Union[str, Path, bytes], filename: str = "document.pdf") -> DocumentCase:
        """
        Ingest a PDF file or binary stream.
        Renders each page to a 300 DPI PNG file in storage/pages/{doc_id}/.
        Reuses cached render if doc_id exists.
        """
        if isinstance(pdf_input, (str, Path)):
            path = Path(pdf_input)
            if not path.exists():
                raise FileNotFoundError(f"PDF file not found at: {path}")
            data = path.read_bytes()
            if filename == "document.pdf":
                filename = path.name
        else:
            data = pdf_input

        doc_id = self.compute_sha256(data)
        doc_dir = self.storage_dir / doc_id
        manifest_path = doc_dir / "manifest.json"

        # Check cache: if already rendered, return cached DocumentCase instantly
        if doc_dir.exists() and manifest_path.exists():
            import json
            manifest_data = json.loads(manifest_path.read_text())
            return DocumentCase(**manifest_data)

        # Fresh render: open with PDFium C++ engine
        doc_dir.mkdir(parents=True, exist_ok=True)
        pdf = pdfium.PdfDocument(data)
        total_pages = len(pdf)
        pages_metadata: List[PageMetadata] = []

        import datetime
        uploaded_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for page_index in range(total_pages):
            page_num = page_index + 1
            page = pdf[page_index]

            # Render at 300 DPI scale factor
            # scale=SCALE_300_DPI renders 72pt grid at 300 DPI
            bitmap = page.render(scale=SCALE_300_DPI)
            pil_image = bitmap.to_pil()

            page_filename = f"page_{page_num}.png"
            page_filepath = doc_dir / page_filename
            pil_image.save(page_filepath, format="PNG", optimize=True)

            width, height = pil_image.size
            pages_metadata.append(
                PageMetadata(
                    page_number=page_num,
                    image_path=str(page_filepath.relative_to(self.storage_dir.parent.parent)),
                    width=width,
                    height=height,
                    has_tables=False,
                    has_charts=False,
                )
            )

        case = DocumentCase(
            doc_id=doc_id,
            filename=filename,
            total_pages=total_pages,
            uploaded_at=uploaded_at,
            pages=pages_metadata,
        )

        # Save manifest for instant sub-millisecond cache hits on repeated uploads
        manifest_path.write_text(case.model_dump_json(indent=2))
        return case

    def ingest_image(self, image_input: Union[str, Path, bytes], filename: str = "image.png") -> DocumentCase:
        """
        Ingest a standalone single image (PNG, JPG, TIFF, WebP).
        Normalizes it into a single-page DocumentCase.
        """
        if isinstance(image_input, (str, Path)):
            path = Path(image_input)
            if not path.exists():
                raise FileNotFoundError(f"Image file not found at: {path}")
            data = path.read_bytes()
            if filename == "image.png":
                filename = path.name
        else:
            data = image_input

        doc_id = self.compute_sha256(data)
        doc_dir = self.storage_dir / doc_id
        manifest_path = doc_dir / "manifest.json"

        if doc_dir.exists() and manifest_path.exists():
            import json
            manifest_data = json.loads(manifest_path.read_text())
            return DocumentCase(**manifest_data)

        doc_dir.mkdir(parents=True, exist_ok=True)
        import io
        img = Image.open(io.BytesIO(data)).convert("RGB")

        page_filepath = doc_dir / "page_1.png"
        img.save(page_filepath, format="PNG", optimize=True)

        import datetime
        uploaded_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        case = DocumentCase(
            doc_id=doc_id,
            filename=filename,
            total_pages=1,
            uploaded_at=uploaded_at,
            pages=[
                PageMetadata(
                    page_number=1,
                    image_path=str(page_filepath.relative_to(self.storage_dir.parent.parent)),
                    width=img.width,
                    height=img.height,
                    has_tables=False,
                    has_charts=False,
                )
            ],
        )

        manifest_path.write_text(case.model_dump_json(indent=2))
        return case


# Module-level alias for hybrid pipeline compatibility
PDFRenderer = DocumentIngestionService

