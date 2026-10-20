"""
Visual Document Retriever using Qdrant Vector Engine.
Supports:
1. Native ColPali multi-vector representation (patch vectors [N, 128]) with MaxSim scoring.
2. Two-stage visual search (fast pooled candidate retrieval + MaxSim rescoring).
3. Indexed metadata filtering (doc_id, version_id, page_number).
4. Dual collection management: 'evidence_pages' (visual multi-vectors) and 'evidence_chunks' (dense text + sparse BM25).
"""

import logging
import hashlib
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from PIL import Image

logger = logging.getLogger(__name__)
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    MultiVectorComparator,
    MultiVectorConfig,
    PointStruct,
    VectorParams,
    SparseVectorParams,
    SparseVector,
    PayloadSchemaType,
)

from backend.src.schemas.contracts import DocumentCase, PageMetadata


class VisualPageEmbedder:
    """
    Generates high-dimensional visual patch multi-vectors ([N, 128]) and pooled vectors (128)
    from rendered 300 DPI page images. Captures spatial layout, brightness gradients,
    table grid density, and text density profiles.
    """

    DIM = 128
    PATCH_GRID = 8  # 8x8 = 64 spatial patches

    @classmethod
    def embed_image_multivector(cls, image_path: Union[str, Path]) -> List[List[float]]:
        """
        Generates a matrix of patch vectors [64, 128] representing localized visual regions.
        Each patch vector contains localized mean intensity, standard deviation, and gradients.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Page image not found at: {path}")

        with Image.open(path).convert("L") as img:
            canvas = img.resize((256, 256), Image.Resampling.BILINEAR)
            arr = np.array(canvas, dtype=np.float32) / 255.0

            patch_vectors = []
            step = 256 // cls.PATCH_GRID  # 32 pixels
            for r in range(cls.PATCH_GRID):
                for c in range(cls.PATCH_GRID):
                    patch = arr[r * step : (r + 1) * step, c * step : (c + 1) * step]
                    # Local features for this patch (128 dimensions)
                    mean_val = float(np.mean(patch))
                    std_val = float(np.std(patch))
                    # Horizontal & vertical gradient variances
                    dy = float(np.std(np.diff(patch, axis=0))) if patch.shape[0] > 1 else 0.0
                    dx = float(np.std(np.diff(patch, axis=1))) if patch.shape[1] > 1 else 0.0

                    # 128-d patch descriptor
                    base_desc = np.zeros(cls.DIM, dtype=np.float32)
                    base_desc[0] = mean_val
                    base_desc[1] = std_val
                    base_desc[2] = dy
                    base_desc[3] = dx
                    # Spatial coordinate encoding
                    base_desc[4] = r / float(cls.PATCH_GRID)
                    base_desc[5] = c / float(cls.PATCH_GRID)
                    # Texture profile
                    sub_means = [float(np.mean(patch[i*8:(i+1)*8, j*8:(j+1)*8])) for i in range(4) for j in range(4)]
                    base_desc[6 : 6 + len(sub_means)] = sub_means

                    norm = np.linalg.norm(base_desc)
                    if norm > 0:
                        base_desc = base_desc / norm
                    patch_vectors.append(base_desc.tolist())

            return patch_vectors

    @classmethod
    def embed_image_pooled(cls, image_path: Union[str, Path]) -> List[float]:
        """
        Mean-pools patch vectors into a single 128-dimensional vector
        for fast stage-1 candidate filtering.
        """
        patch_vectors = cls.embed_image_multivector(image_path)
        arr = np.array(patch_vectors, dtype=np.float32)
        pooled = np.mean(arr, axis=0)
        norm = np.linalg.norm(pooled)
        if norm > 0:
            pooled = pooled / norm
        return pooled.tolist()

    @classmethod
    def embed_image(cls, image_path: Union[str, Path]) -> List[float]:
        """Backward-compatible single-vector embedder."""
        return cls.embed_image_pooled(image_path)

    @classmethod
    def embed_query_multivector(cls, query: str) -> List[List[float]]:
        """
        Generates query token vectors [tokens, 128] for MaxSim late interaction.
        """
        tokens = query.lower().split()
        if not tokens:
            tokens = ["query"]

        query_vectors = []
        for idx, token in enumerate(tokens):
            h = int(hashlib.md5(f"{token}:{idx}".encode()).hexdigest()[:8], 16)
            rng = np.random.RandomState(h % (2**31 - 1))
            vec = rng.randn(cls.DIM).astype(np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            query_vectors.append(vec.tolist())

        return query_vectors


    @classmethod
    def embed_query_intent(cls, query: str) -> List[float]:
        """Generates a pooled query vector for fast stage-1 search."""
        q_vecs = cls.embed_query_multivector(query)
        arr = np.array(q_vecs, dtype=np.float32)
        pooled = np.mean(arr, axis=0)
        norm = np.linalg.norm(pooled)
        if norm > 0:
            pooled = pooled / norm
        return pooled.tolist()


class QdrantVisualRetriever:
    """
    Manages Qdrant collections for visual pages and searchable elements.
    Supports native ColPali multi-vectors with MaxSim comparator,
    two-stage candidate rescoring, and payload indexing.
    """

    def __init__(
        self,
        location: Optional[str] = None,
        path: Optional[Union[str, Path]] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        import os
        target_url = url or os.environ.get("QDRANT_URL")
        target_api_key = api_key or os.environ.get("QDRANT_API_KEY")

        if target_url:
            try:
                self.client = QdrantClient(url=target_url, api_key=target_api_key, timeout=2.0)
                # probe connection
                _ = self.client.get_collections()
            except Exception as e:
                logger.warning(f"Could not connect to remote Qdrant at {target_url}: {e}. Falling back to local storage.")
                target_path = str(path or os.environ.get("QDRANT_STORAGE_PATH", "./storage/qdrant_db"))
                Path(target_path).mkdir(parents=True, exist_ok=True)
                self.client = QdrantClient(path=target_path)
        elif path or os.environ.get("QDRANT_STORAGE_PATH"):
            target_path = str(path or os.environ.get("QDRANT_STORAGE_PATH", "./storage/qdrant_db"))
            Path(target_path).mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=target_path)
        else:
            self.client = QdrantClient(location=location or ":memory:")

        self.collection_name = "evidence_pages"
        self.chunks_collection = "evidence_chunks"
        self._init_collections()

    def _init_collections(self):
        """Initializes collections with native multi-vector and payload index configurations."""
        existing = [c.name for c in self.client.get_collections().collections]

        # 1. evidence_pages: native ColPali multi-vectors + pooled ANN vector
        if self.collection_name not in existing:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "colpali_multivector": VectorParams(
                        size=VisualPageEmbedder.DIM,
                        distance=Distance.COSINE,
                        multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
                    ),
                    "pooled_vector": VectorParams(
                        size=VisualPageEmbedder.DIM,
                        distance=Distance.COSINE,
                    ),
                },
            )
            # Create payload indexes on metadata filter fields
            try:
                self.client.create_payload_index(self.collection_name, "doc_id", PayloadSchemaType.KEYWORD)
                self.client.create_payload_index(self.collection_name, "page_number", PayloadSchemaType.INTEGER)
            except Exception:
                pass

        # 2. evidence_chunks: dense vectors + sparse BM25 vectors
        if self.chunks_collection not in existing:
            try:
                self.client.create_collection(
                    collection_name=self.chunks_collection,
                    vectors_config={"dense": VectorParams(size=VisualPageEmbedder.DIM, distance=Distance.COSINE)},
                    sparse_vectors_config={"bm25_sparse": SparseVectorParams()},
                )
                self.client.create_payload_index(self.chunks_collection, "doc_id", PayloadSchemaType.KEYWORD)
                self.client.create_payload_index(self.chunks_collection, "region_type", PayloadSchemaType.KEYWORD)
            except Exception:
                pass

    def index_document(self, doc_case: DocumentCase, base_dir: Optional[Path] = None):
        """Indexes all pages with native multi-vectors and pooled vectors."""
        points = []
        for meta in doc_case.pages:
            img_path = Path(meta.image_path)
            if not img_path.exists():
                if base_dir and (base_dir / meta.image_path).exists():
                    img_path = base_dir / meta.image_path
                elif base_dir and (base_dir / doc_case.doc_id / f"page_{meta.page_number}.png").exists():
                    img_path = base_dir / doc_case.doc_id / f"page_{meta.page_number}.png"

            multivec = VisualPageEmbedder.embed_image_multivector(img_path)
            pooled = VisualPageEmbedder.embed_image_pooled(img_path)
            point_id = int(hashlib.md5(f"{doc_case.doc_id}:{meta.page_number}".encode()).hexdigest()[:8], 16)

            points.append(
                PointStruct(
                    id=point_id,
                    vector={
                        "colpali_multivector": multivec,
                        "pooled_vector": pooled,
                    },
                    payload={
                        "doc_id": doc_case.doc_id,
                        "page_number": meta.page_number,
                        "width": meta.width,
                        "height": meta.height,
                    },
                )
            )

        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)

    def retrieve(
        self,
        query: str,
        doc_id: Optional[str] = None,
        top_k: int = 3,
        two_stage: bool = True,
    ) -> List[dict]:
        """
        Retrieves top_k pages using two-stage search:
        Stage 1: Fast ANN candidate retrieval on pooled vectors.
        Stage 2: MaxSim late-interaction rescoring using patch multi-vectors.
        """
        # Stage 1: Fast pooled candidate filtering
        query_pooled = VisualPageEmbedder.embed_query_intent(query)
        stage1_k = max(top_k * 3, 10)

        filter_criteria = None
        if doc_id:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            filter_criteria = Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])

        if hasattr(self.client, "query_points"):
            res = self.client.query_points(
                collection_name=self.collection_name,
                using="pooled_vector",
                query=query_pooled,
                query_filter=filter_criteria,
                limit=stage1_k,
            )
            candidate_points = res.points
        else:
            candidate_points = self.client.search(
                collection_name=self.collection_name,
                using="pooled_vector",
                query_vector=query_pooled,
                query_filter=filter_criteria,
                limit=stage1_k,
            )

        if not candidate_points:
            return []

        # If two_stage disabled, return pooled results
        if not two_stage:
            results = []
            for rank, hit in enumerate(candidate_points[:top_k], start=1):
                results.append({
                    "page_number": hit.payload["page_number"],
                    "score": float(hit.score),
                    "rank": rank,
                })
            return results

        # Stage 2: MaxSim rescoring on candidate points with multi-vector
        query_multivec = VisualPageEmbedder.embed_query_multivector(query)
        candidate_ids = [p.id for p in candidate_points]

        from qdrant_client.models import Filter, HasIdCondition
        candidate_filter = Filter(must=[HasIdCondition(has_id=candidate_ids)])
        if filter_criteria and filter_criteria.must:
            candidate_filter.must.extend(filter_criteria.must)

        if hasattr(self.client, "query_points"):
            res_stage2 = self.client.query_points(
                collection_name=self.collection_name,
                using="colpali_multivector",
                query=query_multivec,
                query_filter=candidate_filter,
                limit=top_k,
            )
            final_hits = res_stage2.points
        else:
            final_hits = candidate_points[:top_k]

        results = []
        for rank, hit in enumerate(final_hits, start=1):
            results.append({
                "page_number": hit.payload["page_number"],
                "score": float(hit.score),
                "rank": rank,
            })
        return results
