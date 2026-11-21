"""Hermetic stand-in for sentence_transformers, injected via PYTHONPATH.

Deterministic "embeddings": normalized counts of a tiny fixed vocabulary, so
tests can construct queries with known nearest neighbors.
"""

VOCAB = ["hello", "second", "caption", "summary", "frame", "stub"]


class SentenceTransformer:
    def __init__(self, name):
        self.name = name

    def encode(self, texts, **kwargs):
        out = []
        for t in texts:
            tl = t.lower()
            v = [float(tl.count(w)) for w in VOCAB]
            norm = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / norm for x in v])
        return out
