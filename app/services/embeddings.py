from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from app.services.lexicon import STOPWORDS

DIM = 512
WORD_RE = re.compile(r"[a-z0-9+#.]+")


def _tokens(text: str) -> list[str]:
    words = [w for w in WORD_RE.findall((text or "").lower()) if len(w) > 1 and w not in STOPWORDS]
    bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:])]
    return words + bigrams


@lru_cache(maxsize=4096)
def embed(text: str) -> tuple[float, ...]:
    """Deterministic hashing embedding (no model download, laptop friendly)."""
    vec = [0.0] * DIM
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        h = int.from_bytes(digest, "big")
        idx = h % DIM
        sign = 1.0 if (h >> 63) & 1 == 0 else -1.0
        vec[idx] += sign
    norm_val = math.sqrt(sum(v * v for v in vec))
    if norm_val:
        vec = [v / norm_val for v in vec]
    return tuple(vec)


def similarity(a: str, b: str) -> float:
    va, vb = embed(a), embed(b)
    dot = sum(x * y for x, y in zip(va, vb))
    return max(0.0, min(1.0, dot))
