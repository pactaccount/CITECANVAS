"""
Document ingestion with fast previews and on-demand evidence renders.

Every upload retains its original PDF. Uploads create compact page previews so
the browser becomes usable quickly; a lossless 300-DPI page is rendered only
when visual verification or a high-resolution source view needs it.
"""

import hashlib
import os
from pathlib import Path
from typing import Union, List, Optional
from PIL import Image
import pypdfium2 as pdfium

from backend.src.schemas.contracts import DocumentCase, PageMetadata


# A preview is sufficient for browsing and source navigation. Evidence work
# always requests the 300-DPI path below, so this does not lower answer
# verification quality.
PREVIEW_DPI = int(os.getenv("EVID_PREVIEW_DPI", "180"))
EVIDENCE_DPI = int(os.getenv("EVID_EVIDENCE_DPI", "300"))
# Public compatibility constant: callers that explicitly request the historic
# high-resolution scale still receive the same 300-DPI value.
SCALE_300_DPI = EVIDENCE_DPI / 72.0


class DocumentIngestionService:
    """
    Ingests PDF documents or standalone images, renders them to preview PNGs,
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
        Renders each page to a compact preview PNG file in storage/pages/{doc_id}/.
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

            bitmap = page.render(scale=PREVIEW_DPI / 72.0)
            pil_image = bitmap.to_pil()

            page_filename = f"page_{page_num}.png"
            page_filepath = doc_dir / page_filename
            # PNG optimisation is CPU-heavy and offers little benefit for
            # rendered pages. Fast, lossless compression keeps uploads quick.
            pil_image.save(page_filepath, format="PNG", optimize=False, compress_level=2)

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

    @staticmethod
    def render_evidence_page(pdf_input: Union[str, Path, bytes], page_number: int, output_path: Union[str, Path]) -> Path:
        """Render one lossless 300-DPI page only when evidence work needs it."""
        if page_number < 1:
            raise ValueError("page_number must be at least 1")
        pdf = pdfium.PdfDocument(pdf_input)
        if page_number > len(pdf):
            raise ValueError("page_number exceeds document length")
        path = Path(output_path)
        if path.is_file():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        image = pdf[page_number - 1].render(scale=EVIDENCE_DPI / 72.0).to_pil()
        temp = path.with_suffix(".tmp")
        image.save(temp, format="PNG", optimize=False)
        temp.replace(path)
        return path

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

