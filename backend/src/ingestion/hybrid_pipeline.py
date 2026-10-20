"""
Master Hybrid Ingestion Pipeline Orchestrator (Steps 1-14).
Executes end-to-end ingestion:
1. Document fingerprinting (SHA-256) & versioning
2. Page-level quality and text-layer assessment
3. Native text extraction with coordinates
4. Selective image preprocessing (contrast, deskew)
5. Layout-aware parsing (headings, paragraphs)
6. Selective OCR fallback for damaged layers
7. Structured table extraction (cells, headers, coordinates, numeric parsing)
8. Stamp / seal detection and recognition
9. Signature-region detection
10. Formula and figure enrichment
11. Structure-aware text chunking (HybridChunker, 400-700 tokens)
12. Visual multi-vector embedding (ColPali/Qdrant)
13. Text and keyword indexing (BM25 + Dense + Identifiers)
14. Quality flags and source provenance tracking

Stores three connected representations:
- Original evidence: original PDF, 300 DPI page images, retrieval images, crops
- Structured document: JSON representation in storage/structured/
- Search indexes: payloads for Qdrant text_regions and visual_pages
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from PIL import Image

from backend.src.ingestion.fingerprint import DocumentFingerprinter
from backend.src.ingestion.quality_assessor import QualityAssessor
from backend.src.ingestion.native_text import NativeTextExtractor
from backend.src.ingestion.preprocessor import ImagePreprocessor
from backend.src.ingestion.layout_parser import LayoutParser
from backend.src.ingestion.hybrid_chunker import HybridChunker
from backend.src.ingestion.pdf_renderer import PDFRenderer
from backend.src.retrieval.visual_indexer import VisualPageEmbedder, QdrantVisualRetriever
from backend.src.retrieval.bm25_indexer import BM25Retriever
from backend.src.schemas.contracts import (
    DocumentCase,
    DocumentRegion,
    PageMetadata,
    StructuredDocument,
    StructuredTable,
)


class HybridIngestionPipeline:
    """
    Orchestrates the 14-step hybrid document ingestion lifecycle.
    """

    def __init__(self, base_storage_dir: Optional[Union[str, Path]] = None):
        if base_storage_dir is None:
            self.base_dir = Path(__file__).resolve().parent.parent.parent.parent / "storage"
        else:
            self.base_dir = Path(base_storage_dir)

        self.pages_dir = self.base_dir / "pages"
        self.crops_dir = self.base_dir / "crops"
        self.structured_dir = self.base_dir / "structured"

        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.crops_dir.mkdir(parents=True, exist_ok=True)
        self.structured_dir.mkdir(parents=True, exist_ok=True)

    def ingest_document(
        self,
        pdf_path: Union[str, Path],
        index_to_qdrant: bool = True,
        qdrant_retriever: Optional[QdrantVisualRetriever] = None,
    ) -> DocumentCase:
        """
        Executes complete hybrid ingestion across all 14 steps.
        """
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_file}")

        # Step 1: Document fingerprinting and versioning
        doc_id = DocumentFingerprinter.compute_sha256(pdf_file)
        version_record = DocumentFingerprinter.create_version_record(doc_id=doc_id)
        version_id = version_record.version_id

        doc_pages_dir = self.pages_dir / doc_id
        doc_pages_dir.mkdir(parents=True, exist_ok=True)

        # Render 300 DPI master pages + create retrieval-scale images (1400px)
        renderer = PDFRenderer(storage_dir=self.pages_dir)
        initial_case = renderer.ingest_pdf(pdf_file)
        total_pages = initial_case.total_pages

        pages_metadata: List[PageMetadata] = []
        all_regions: List[DocumentRegion] = []
        all_tables: List[StructuredTable] = []
        document_quality_flags: List[str] = []

        # Iterate through pages
        for page_num in range(1, total_pages + 1):
            master_image_path = doc_pages_dir / f"page_{page_num}.png"

            # Create retrieval-scale image (max dimension 1400px)
            retrieval_image_path = doc_pages_dir / f"page_{page_num}_retrieval.jpg"
            if not retrieval_image_path.exists() and master_image_path.exists():
                with Image.open(master_image_path) as img:
                    w, h = img.size
                    max_dim = 1400
                    if max(w, h) > max_dim:
                        scale = max_dim / float(max(w, h))
                        retrieval_img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)
                    else:
                        retrieval_img = img.copy()
                    retrieval_img.convert("RGB").save(retrieval_image_path, format="JPEG", quality=88, optimize=True)

            # Step 2: Page-level quality and text-layer assessment
            quality = QualityAssessor.assess_page(
                pdf_path=pdf_file,
                page_number=page_num,
                page_image_path=master_image_path,
            )
            document_quality_flags.extend(quality.quality_flags)

            # Step 4: Selective image preprocessing (only if needed)
            processed_img_path, was_preprocessed = ImagePreprocessor.process_page_image_selectively(
                image_path=master_image_path,
                assessment=quality,
            )
            if was_preprocessed:
                document_quality_flags.append(f"p{page_num}_preprocessed")

            # Step 3: Native text extraction with coordinates
            native_regions = NativeTextExtractor.extract_page_regions(
                pdf_path=pdf_file,
                page_number=page_num,
                doc_id=doc_id,
                version_id=version_id,
                text_layer_valid=quality.text_layer_valid,
            )

            # Steps 5-10: Layout-aware parsing, structured tables, stamps, signatures, equations
            layout_regions, tables = LayoutParser.parse_page(
                pdf_path=pdf_file,
                page_number=page_num,
                doc_id=doc_id,
                version_id=version_id,
                quality=quality,
            )

            # Reconcile native regions with layout regions
            combined_page_regions = layout_regions if layout_regions else native_regions
            all_regions.extend(combined_page_regions)
            all_tables.extend(tables)

            has_tables = len(tables) > 0
            has_charts = any(r.region_type in ("figure", "chart") for r in combined_page_regions)
            has_stamps = any(r.region_type == "stamp" for r in combined_page_regions)
            has_signatures = any(r.region_type == "signature" for r in combined_page_regions)

            meta = PageMetadata(
                page_number=page_num,
                image_path=str(master_image_path.relative_to(self.base_dir)),
                retrieval_image_path=str(retrieval_image_path.relative_to(self.base_dir)),
                width=2481,
                height=3508,
                quality=quality,
                has_tables=has_tables,
                has_charts=has_charts,
                has_stamps=has_stamps,
                has_signatures=has_signatures,
                regions_count=len(combined_page_regions),
            )
            pages_metadata.append(meta)

        # Step 11: Structure-aware text chunking with parent-section links
        searchable_chunks = HybridChunker.chunk_document_regions(
            regions=all_regions,
            tables=all_tables,
        )

        # Collect page texts for logical document organization
        from backend.src.ingestion.text_extractor import TextExtractionService
        page_texts = TextExtractionService.extract_from_pdf(pdf_file)

        # Execute Document Organization (Steps 1-12)
        from backend.src.organization.organizer import DocumentOrganizer
        (
            logical_docs,
            sections,
            all_relationships,
            extracted_fields,
            temporal_record,
            domain_ext,
            catalog_record,
        ) = DocumentOrganizer.organize_document(
            doc_id=doc_id,
            version_id=version_id,
            pages=pages_metadata,
            regions=searchable_chunks,
            tables=all_tables,
            page_texts=page_texts,
        )

        # Representation 2: Build StructuredDocument (JSON representation)
        structured_doc = StructuredDocument(
            document_id=doc_id,
            version_id=version_id,
            filename=pdf_file.name,
            sha256_hash=doc_id,
            total_pages=total_pages,
            processing_version=version_record,
            pages=pages_metadata,
            logical_documents=logical_docs,
            sections=sections,
            regions=searchable_chunks,
            tables=all_tables,
            relationships=all_relationships,
            extracted_fields=extracted_fields,
            temporal_record=temporal_record,
            domain_extension=domain_ext,
            faceted_catalog=catalog_record,
            quality_flags=list(set(document_quality_flags)),
        )

        # Save Representation 2 to disk
        structured_json_path = self.structured_dir / f"{doc_id}_v{version_id}.json"
        with open(structured_json_path, "w", encoding="utf-8") as f:
            f.write(structured_doc.model_dump_json(indent=2))

        # Representation 3: Search Indexing (Qdrant Visual + BM25)
        doc_case = DocumentCase(
            doc_id=doc_id,
            filename=pdf_file.name,
            total_pages=total_pages,
            uploaded_at=version_record.created_at,
            pages=pages_metadata,
            structured_doc=structured_doc,
        )

        if index_to_qdrant:
            retriever = qdrant_retriever or QdrantVisualRetriever()
            retriever.index_document(doc_case, base_dir=self.base_dir)

        return doc_case
