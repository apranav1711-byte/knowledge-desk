"""Embedding backends. Production: BAAI/bge-small-en-v1.5 (384-d, ONNX/CPU via fastembed).

BGE invariant: queries carry the retrieval instruction prefix; passages do not.
The `hash` backend is a deterministic offline stand-in used by tests and for running without a model download.
"""
from __future__ import annotations

import hashlib
import re
import threading

import numpy as np

from app.core.config import settings

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
DIM = 384


class HashEmbedder:
    name = "hash-bow-384"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(DIM, dtype=np.float32)
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % DIM] += 1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t).tolist() for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text).tolist()


class BgeEmbedder:
    def __init__(self):
        from fastembed import TextEmbedding

        settings.MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.name = settings.EMBEDDING_MODEL
        self._model = TextEmbedding(model_name=settings.EMBEDDING_MODEL, cache_dir=str(settings.MODEL_CACHE_DIR))
        self._lock = threading.Lock()

    def _embed(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            out = []
            for v in self._model.embed(texts, batch_size=16):
                v = np.asarray(v, dtype=np.float32)
                n = np.linalg.norm(v)
                out.append((v / n if n else v).tolist())
            return out

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([QUERY_PREFIX + text])[0]


_embedder = None
_lock = threading.Lock()


def get_embedder():
    global _embedder
    with _lock:
        if _embedder is None:
            _embedder = HashEmbedder() if settings.EMBEDDING_BACKEND == "hash" else BgeEmbedder()
        return _embedder
