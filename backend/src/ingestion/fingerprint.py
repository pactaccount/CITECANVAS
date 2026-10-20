"""
Document Fingerprinting & Versioning Module (Step 1).
Computes SHA-256 hash, generates deterministic document_id and version_id,
and records the processing version metadata.
"""

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from backend.src.schemas.contracts import ProcessingVersion


class DocumentFingerprinter:
    """
    Manages document hashing, version tracking, and processing provenance.
    """

    @staticmethod
    def compute_sha256(file_path: Union[str, Path]) -> str:
        """Computes SHA-256 cryptographic digest of a file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found for fingerprinting: {path}")

        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    @staticmethod
    def create_version_record(
        doc_id: str,
        pipeline_version: str = "v3.0-hybrid",
        primary_parser: str = "docling_with_pdfium_fallback",
        ocr_engine: str = "rapid_ocr_paddle_fallback",
        embedding_model: str = "bge-m3",
        visual_model: str = "colpali-qdrant",
    ) -> ProcessingVersion:
        """
        Creates an immutable ProcessingVersion record for provenance tracking.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        # Deterministic version id combining doc_id, pipeline version, and current date
        v_seed = f"{doc_id}:{pipeline_version}:{timestamp[:10]}"
        version_id = hashlib.md5(v_seed.encode()).hexdigest()[:8]

        return ProcessingVersion(
            version_id=version_id,
            document_id=doc_id,
            pipeline_version=pipeline_version,
            primary_parser=primary_parser,
            ocr_engine=ocr_engine,
            embedding_model=embedding_model,
            visual_model=visual_model,
            created_at=timestamp,
        )
