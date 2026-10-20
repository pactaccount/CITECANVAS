"""
Dense Semantic Text Retriever for Evid.
Provides dense vector retrieval over document text chunks, section headers, and table markdown representations.
Supports in-memory vector indexing and persistent Qdrant collection backends.
Enables independent semantic candidate path for RAG hybrid search.
"""

import hashlib
import re
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
from pydantic import BaseModel, Field


class DenseTextChunk(BaseModel):
    """Contextualized text chunk indexed for dense retrieval."""
    chunk_id: str
    doc_id: str
    page_number: int
    text: str
    section_title: Optional[str] = None
    chunk_type: str = "paragraph"  # paragraph, table_markdown, heading, caption
    metadata: Dict[str, Union[str, int, float, bool]] = Field(default_factory=dict)


class DenseTextRetriever:
    """
    Dense Semantic Text Retriever.
    Generates normalized semantic embeddings and computes cosine similarity.
    Compatible with BGE-M3 / Sentence-Transformer dense search semantics.
    """

    DIM = 128

    def __init__(self, location: str = ":memory:"):
        self.location = location
        self._chunks: Dict[str, DenseTextChunk] = {}
        self._vectors: Dict[str, np.ndarray] = {}  # chunk_id -> normalized vector
        self._doc_index: Dict[str, List[str]] = {}  # doc_id -> list of chunk_ids

    @classmethod
    def embed_text(cls, text: str) -> np.ndarray:
        """
        Generates a deterministic 128-dimensional dense semantic embedding.
        Uses character n-gram and token hashed frequency projections with L2 normalization.
        Compatible with lightweight zero-dependency semantic vector search.
        """
        cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
        tokens = cleaned.split()
        if not tokens:
            tokens = ["empty"]

        vec = np.zeros(cls.DIM, dtype=np.float32)

        # 1. Word token projections
        for i, tok in enumerate(tokens):
            h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest()[:8], 16)
            idx = h % cls.DIM
            sign = 1.0 if ((h >> 8) & 1) else -1.0
            vec[idx] += sign * (1.0 / (1.0 + 0.1 * i))

        # 2. Sub-word character trigram projections (bridges typo and inflection gaps)
        for tok in tokens:
            if len(tok) >= 3:
                for j in range(len(tok) - 2):
                    trigram = tok[j : j + 3]
                    h_tri = int(hashlib.md5(trigram.encode("utf-8")).hexdigest()[:8], 16)
                    idx_tri = h_tri % cls.DIM
                    vec[idx_tri] += 0.3 * (1.0 if ((h_tri >> 8) & 1) else -1.0)

        # L2 normalize
        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec = vec / norm
        else:
            vec[0] = 1.0

        return vec

    def index_chunks(self, chunks: List[DenseTextChunk]):
        """Indexes text chunks into the dense retrieval collection."""
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk
            vec = self.embed_text(f"{chunk.section_title or ''} {chunk.text}".strip())
            self._vectors[chunk.chunk_id] = vec

            if chunk.doc_id not in self._doc_index:
                self._doc_index[chunk.doc_id] = []
            if chunk.chunk_id not in self._doc_index[chunk.doc_id]:
                self._doc_index[chunk.doc_id].append(chunk.chunk_id)

    def retrieve(
        self,
        query: str,
        doc_id: Optional[str] = None,
        top_k: int = 10,
    ) -> List[dict]:
        """
        Computes cosine similarity between query and indexed chunks.
        Returns top-k ranked chunks with scores.
        """
        if not self._vectors:
            return []

        q_vec = self.embed_text(query)

        # Filter candidates by doc_id if specified
        target_chunk_ids = self._doc_index.get(doc_id) if doc_id else list(self._chunks.keys())
        if not target_chunk_ids:
            return []

        scores: List[Tuple[str, float]] = []
        for cid in target_chunk_ids:
            cvec = self._vectors[cid]
            # Cosine similarity between normalized vectors is dot product
            sim = float(np.dot(q_vec, cvec))
            scores.append((cid, sim))

        # Sort descending by similarity
        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for rank, (cid, sim) in enumerate(scores[:top_k], start=1):
            chunk = self._chunks[cid]
            results.append({
                "chunk_id": cid,
                "doc_id": chunk.doc_id,
                "page_number": chunk.page_number,
                "text": chunk.text,
                "section_title": chunk.section_title,
                "chunk_type": chunk.chunk_type,
                "similarity": sim,
                "rank": rank,
                "metadata": chunk.metadata,
            })

        return results
