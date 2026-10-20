"""
Duplicate & Near-Duplicate Grouping Engine (Step 9).
Uses cryptographic SHA-256 for exact duplicates and normalized token Jaccard similarity
for near-duplicate revision grouping (e.g., Draft vs Final, Revision A vs Revision B).
"""

import hashlib
import re
from typing import List, Set, Tuple


class DuplicateDetector:
    """
    Groups identical documents and detects near-duplicate revisions.
    """

    @staticmethod
    def get_token_shingles(text: str, k: int = 2) -> Set[str]:
        """Creates word unigrams and bigrams for robust similarity estimation."""
        words = re.findall(r'\w+', text.lower())
        shingles = set(words)  # Include unigrams
        for i in range(len(words) - 1):
            shingles.add(f"{words[i]}_{words[i+1]}")
        return shingles

    @classmethod
    def calculate_jaccard_similarity(cls, text_a: str, text_b: str) -> float:
        """Calculates Jaccard similarity between token shingles."""
        set_a = cls.get_token_shingles(text_a)
        set_b = cls.get_token_shingles(text_b)
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a.intersection(set_b))
        union = len(set_a.union(set_b))
        return intersection / float(union) if union > 0 else 0.0

    @classmethod
    def is_near_duplicate(cls, text_a: str, text_b: str, threshold: float = 0.85) -> Tuple[bool, float]:
        """
        Returns (True, score) if documents share >= 85% near-identical shingle overlap.
        Preserves both revisions while grouping them under a common family.
        """
        score = cls.calculate_jaccard_similarity(text_a, text_b)
        return (score >= threshold), round(score, 3)
