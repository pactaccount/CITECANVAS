#!/usr/bin/env python3 -I
"""Baseline text retrieval with rank-bm25 — deterministic, no paid API.
Label: deterministic baseline (not learned model).
"""
from rank_bm25 import BM25Okapi

class ProcedureRetrieval:
    def __init__(self, docs):
        # docs: list of strings (procedure passages)
        self.docs = docs
        tokenized = [d.lower().split() for d in docs]
        self.bm25 = BM25Okapi(tokenized)
    def retrieve(self, query, top_k=3):
        tokenized = query.lower().split()
        scores = self.bm25.get_scores(tokenized)
        # Deterministic ranking; same query always same order.
        idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [{"doc": self.docs[i], "score": float(scores[i])} for i in idx]
