"""Search over the knowledge base: embeddings + keywords + the precedence rules.

The index only holds chunks of current documents (see kb.py), so deprecated and
draft documents can never be returned. On top of that this module applies:
  - department filter: a document that does not apply to the employee's department is skipped;
  - exact error-code match: a chunk that contains the code from the employee's message wins;
  - authority: non-authoritative documents (KB-017) are only a fallback.
"""
import hashlib
import logging
import re
from dataclasses import dataclass, field

import numpy as np

from app import config, kb
from app.guardrails import CODE

log = logging.getLogger("helpdesk.retrieval")

TOKEN = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")
STOPWORDS = {"the", "and", "for", "with", "that", "this", "from", "have", "has", "was", "are", "not",
             "you", "your", "can", "how", "what", "when", "why", "does", "doesn", "when", "all", "any"}


@dataclass
class Hit:
    chunk: kb.Chunk
    doc: kb.Doc
    score: float
    parts: dict = field(default_factory=dict)   # how the score was made, for explain_search.py


def tokens(text: str) -> set[str]:
    return {t for t in TOKEN.findall(text.lower()) if len(t) > 2 and t not in STOPWORDS}


class Index:
    def __init__(self, docs: dict[str, kb.Doc], chunks: list[kb.Chunk], vectors: np.ndarray | None):
        self.docs = docs
        self.chunks = chunks
        self.vectors = vectors                                  # None = keyword-only mode
        self.chunk_tokens = [tokens(c.text) for c in chunks]
        # Every error code the knowledge base documents. A code outside this set has no documented fix.
        self.known_codes = {c for d in kb.searchable_docs(docs) for c in d.error_codes}
        for chunk in chunks:
            self.known_codes |= set(CODE.findall(chunk.text))

    @property
    def has_vectors(self) -> bool:
        return self.vectors is not None

    @classmethod
    async def build(cls, docs: dict[str, kb.Doc], llm) -> "Index":
        chunks = kb.build_chunks(docs)
        vectors = await _load_or_embed(chunks, llm)
        log.info("index ready: %d chunks, %s", len(chunks), "embeddings" if vectors is not None else "keywords only")
        return cls(docs, chunks, vectors)

    def search(self, query: str, query_vec: list[float] | None, department: str | None,
               codes: list[str], k: int = config.TOP_K) -> list[Hit]:
        q_tokens = tokens(query)
        cosine = None
        if self.vectors is not None and query_vec is not None:
            q = np.asarray(query_vec, dtype=np.float32)
            cosine = self.vectors @ (q / (np.linalg.norm(q) or 1.0))

        hits = []
        for i, chunk in enumerate(self.chunks):
            doc = self.docs[chunk.doc_id]
            if department and "all" not in doc.applies_to and department not in doc.applies_to:
                continue
            overlap = len(q_tokens & self.chunk_tokens[i]) / (len(q_tokens) or 1)
            # With embeddings, keywords only nudge the score. Without them they are the score.
            base = float(cosine[i]) + 0.25 * overlap if cosine is not None else overlap
            code_bonus = 0.0
            for code in codes:
                if code in chunk.text:
                    code_bonus += 0.4
                elif code in doc.error_codes:
                    code_bonus += 0.1
            security = 0.05 if doc.id.startswith("SP-") else 0.0     # precedence rule 1: security policies first
            authority = 0.0 if doc.authoritative else -0.10
            parts = {"cosine": None if cosine is None else round(float(cosine[i]), 3), "keywords": round(overlap, 3),
                     "code": code_bonus, "security_policy": security, "authority": authority}
            hits.append(Hit(chunk, doc, base + code_bonus + security + authority, parts))

        hits.sort(key=lambda h: h.score, reverse=True)
        hits = hits[:k]

        # Authority rule: a non-authoritative document (the FAQ) is only used when no
        # authoritative document is relevant. KB-017 is wrong about SMS codes and the P1 threshold.
        if any(h.doc.authoritative and h.score >= config.MIN_EVIDENCE_SCORE for h in hits):
            hits = [h for h in hits if h.doc.authoritative]
        return hits

    @staticmethod
    def relevant(hits: list[Hit]) -> list[Hit]:
        """The hits strong enough to answer from. Empty means: the KB has no answer."""
        return [h for h in hits if h.score >= config.MIN_EVIDENCE_SCORE]


async def _load_or_embed(chunks: list[kb.Chunk], llm) -> np.ndarray | None:
    """Embed every chunk once and keep the result on disk, keyed by the chunk texts."""
    key = hashlib.sha256((config.EMBEDDING_MODEL + "\n".join(c.text for c in chunks)).encode()).hexdigest()[:16]
    path = config.CACHE_DIR / f"kb-{key}.npy"
    if path.is_file():
        return np.load(path)
    try:
        vectors = []
        for start in range(0, len(chunks), 64):
            vectors += await llm.embed([c.text for c in chunks[start:start + 64]])
        matrix = np.asarray(vectors, dtype=np.float32)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)    # unit length: dot product = cosine
        config.CACHE_DIR.mkdir(exist_ok=True)
        np.save(path, matrix)
        return matrix
    except Exception as exc:  # noqa: BLE001 - any failure means: fall back to keywords
        log.warning("embeddings unavailable (%s: %s); using keyword search only", exc.__class__.__name__, exc)
        return None
