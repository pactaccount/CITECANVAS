"""
Persistent Lexical Keyword Indexer with True Inverted Posting Lists.
Supports:
1. Inverted posting lists (term -> [(doc_idx, tf)]) for fast candidate filtering.
2. Disk persistence (save/load) for production restarts.
3. Qdrant sparse vector formatting (term-hash indices and BM25 weights).
4. Code-preserving alphanumeric tokenization.
"""

import json
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from rank_bm25 import BM25Okapi


class BM25Retriever:
    """
    Persistent BM25 lexical retriever with precomputed inverted posting lists
    and Qdrant sparse vector export.
    """

    def __init__(
        self,
        pages_text: Optional[Dict[int, str]] = None,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        self.k1 = k1
        self.b = b
        self.page_numbers: List[int] = []
        self.corpus: List[List[str]] = []
        self.bm25: Optional[BM25Okapi] = None
        # True inverted posting list: term -> [(doc_index, term_frequency)]
        self.inverted_index: Dict[str, List[Tuple[int, int]]] = {}
        self.doc_lengths: List[int] = []
        self.avg_doc_length: float = 0.0

        if pages_text:
            self.index_pages(pages_text)

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """
        Tokenizes text while preserving hyphenated codes, currency symbols, and numbers.
        E.g., '$554' -> ['$554', '554'], 'HP-400' -> ['hp-400', 'hp', '400'].
        """
        text = text.lower()
        raw_tokens = re.findall(r"[\$\%\w]+(?:[-/][\$\%\w]+)*", text)
        tokens = []
        for t in raw_tokens:
            tokens.append(t)
            if "-" in t:
                tokens.extend(t.split("-"))
            if t.startswith("$") and len(t) > 1:
                tokens.append(t[1:])
        return tokens

    def index_pages(self, pages_text: Dict[int, str]):
        """
        Builds BM25 index and genuine inverted posting lists from page dictionary.
        """
        self.page_numbers = sorted(pages_text.keys())
        self.corpus = [self.tokenize(pages_text[p]) for p in self.page_numbers]
        self.doc_lengths = [len(c) for c in self.corpus]
        self.avg_doc_length = sum(self.doc_lengths) / max(1, len(self.doc_lengths))

        # Build genuine inverted posting list
        self.inverted_index = {}
        for doc_idx, tokens in enumerate(self.corpus):
            term_counts: Dict[str, int] = {}
            for t in tokens:
                term_counts[t] = term_counts.get(t, 0) + 1
            for term, count in term_counts.items():
                if term not in self.inverted_index:
                    self.inverted_index[term] = []
                self.inverted_index[term].append((doc_idx, count))

        if self.corpus:
            self.bm25 = BM25Okapi(self.corpus, k1=self.k1, b=self.b)

    def retrieve(self, query: str, top_k: int = 3) -> List[dict]:
        """
        Retrieves top_k pages for a given query string using BM25 scoring.
        Returns a list of dicts: [{'page_number': int, 'score': float, 'rank': int}]
        """
        if not self.bm25 or not self.corpus:
            return []

        tokenized_query = self.tokenize(query)
        if not tokenized_query:
            return []

        scores = self.bm25.get_scores(tokenized_query)
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results = []
        for rank, idx in enumerate(ranked_indices[:top_k], start=1):
            if scores[idx] > 0.0 or rank == 1:
                results.append({
                    "page_number": self.page_numbers[idx],
                    "score": float(scores[idx]),
                    "rank": rank,
                })

        return results

    def to_qdrant_sparse_vector(self, text: str) -> Dict[str, List]:
        """
        Converts text into a Qdrant-compatible sparse vector:
        {'indices': List[int], 'values': List[float]}
        using 32-bit term hashes and BM25 term weights.
        """
        tokens = self.tokenize(text)
        if not tokens or not self.bm25:
            return {"indices": [], "values": []}

        # Compute term frequency in this text
        tf_map: Dict[str, int] = {}
        for t in tokens:
            tf_map[t] = tf_map.get(t, 0) + 1

        sparse_dict: Dict[int, float] = {}
        doc_len = len(tokens)

        for term, freq in tf_map.items():
            # Hash term to unsigned 32-bit integer index
            term_hash = abs(hash(term)) % (2**31 - 1)
            # Compute IDF weight from precomputed BM25 model if available
            idf = self.bm25.idf.get(term, 1.0) if hasattr(self.bm25, "idf") else 1.0
            # Standard BM25 term weight
            numerator = freq * (self.k1 + 1)
            denominator = freq + self.k1 * (1 - self.b + self.b * (doc_len / max(1.0, self.avg_doc_length)))
            weight = idf * (numerator / max(0.001, denominator))
            sparse_dict[term_hash] = float(weight)

        sorted_indices = sorted(sparse_dict.keys())
        return {
            "indices": sorted_indices,
            "values": [sparse_dict[i] for i in sorted_indices],
        }

    def save_to_disk(self, file_path: Union[str, Path]):
        """Persists the BM25 index and posting lists to a JSON file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "page_numbers": self.page_numbers,
            "doc_lengths": self.doc_lengths,
            "avg_doc_length": self.avg_doc_length,
            "k1": self.k1,
            "b": self.b,
            "corpus": self.corpus,
            "inverted_index": {
                term: postings for term, postings in self.inverted_index.items()
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    @classmethod
    def load_from_disk(cls, file_path: Union[str, Path]) -> "BM25Retriever":
        """Loads a persistent BM25 index from disk."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"BM25 index not found at: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        retriever = cls(k1=data.get("k1", 1.5), b=data.get("b", 0.75))
        retriever.page_numbers = data["page_numbers"]
        retriever.doc_lengths = data["doc_lengths"]
        retriever.avg_doc_length = data["avg_doc_length"]
        retriever.corpus = data["corpus"]
        retriever.inverted_index = {
            k: [tuple(p) for p in v] for k, v in data["inverted_index"].items()
        }
        if retriever.corpus:
            retriever.bm25 = BM25Okapi(retriever.corpus, k1=retriever.k1, b=retriever.b)

        return retriever
