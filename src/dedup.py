"""Exact + near-duplicate detection.

Exact: hash of whitespace-collapsed normalised text.
Near: MinHash (NUM_PERM perms over character SHINGLE-grams) + banded LSH to find
candidates; a candidate is a duplicate when the *signature-estimated Jaccard* >= threshold.
Everything is seeded and vectorised with numpy; no Python hash() (it is salted per process).
Only kept docs are indexed, so every dup_of points at a kept canonical document, and the
canonical is always the earliest in the deterministic input order.
"""
import hashlib
import zlib
import numpy as np
from . import config as C

P = (1 << 31) - 1
_rng = np.random.RandomState(C.MINHASH_SEED)
_A = _rng.randint(1, P, size=C.NUM_PERM, dtype=np.int64).astype(np.uint64)
_B = _rng.randint(0, P, size=C.NUM_PERM, dtype=np.int64).astype(np.uint64)
_PP = np.uint64(P)
_PRIME = np.uint64(1000003)


def exact_key(text: str) -> bytes:
    return hashlib.blake2b(" ".join(text.split()).encode("utf-8"), digest_size=16).digest()


def shingle_hashes(text: str, k: int = None) -> np.ndarray:
    k = k or C.SHINGLE
    s = " ".join(text.casefold().split())
    arr = np.frombuffer(s.encode("utf-32-le"), dtype=np.uint32).astype(np.uint64)
    n = len(arr)
    if n < k:
        return np.array([zlib.crc32(s.encode("utf-8")) % P], dtype=np.uint64)
    m = n - k + 1
    h = np.zeros(m, dtype=np.uint64)
    with np.errstate(over="ignore"):
        for j in range(k):
            h = h * _PRIME + arr[j:j + m]
        h = (h ^ (h >> np.uint64(29))) % _PP
    h = np.unique(h)
    return h[: C.MAX_SHINGLES]


def signature(hs: np.ndarray) -> np.ndarray:
    sig = np.full(C.NUM_PERM, P, dtype=np.uint64)
    for i in range(0, len(hs), 4096):
        blk = hs[i:i + 4096]
        v = (_A[:, None] * blk[None, :] + _B[:, None]) % _PP
        sig = np.minimum(sig, v.min(axis=1))
    return sig.astype(np.uint32)


class NearDedup:
    def __init__(self, threshold=None, bands=None, rows=None):
        self.th = C.NEAR_THRESHOLD if threshold is None else threshold
        self.bands = bands or C.BANDS
        self.rows = rows or C.ROWS
        assert self.bands * self.rows <= C.NUM_PERM
        self.sigs, self.ids = [], []
        self.tables = [dict() for _ in range(self.bands)]

    def query_add(self, doc_id, text):
        """Return (canonical_id, est_jaccard) if near-dup of an earlier kept doc, else index it."""
        sig = signature(shingle_hashes(text))
        keys = [sig[b * self.rows:(b + 1) * self.rows].tobytes() for b in range(self.bands)]
        cands = set()
        for t, k in zip(self.tables, keys):
            cands.update(t.get(k, ()))
        best, best_s = None, 0.0
        for c in sorted(cands):
            s = float((self.sigs[c] == sig).mean())
            if s >= self.th and s > best_s:
                best, best_s = c, s
        if best is not None:
            return self.ids[best], best_s
        idx = len(self.ids)
        self.ids.append(doc_id)
        self.sigs.append(sig)
        for t, k in zip(self.tables, keys):
            t.setdefault(k, []).append(idx)
        return None, 0.0
