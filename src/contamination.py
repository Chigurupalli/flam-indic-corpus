"""Eval-vs-train leak detection. One Detector holds an index of the eval items and
checks each training doc against it in a single streaming pass.

Methods (priority order when several fire for one pair):
  exact        eval passage is a verbatim substring of the (already normalised) train text
  normalized   substring after aggressive key-folding (casefold, punctuation/whitespace/digit-script removed)
  near         >= CONTAM_NEAR of the eval item's word 4-grams occur in the train doc
  cross_script Devanagari eval item whose consonant skeleton (src/translit.py) is
               >= XS_THRESHOLD contained in a Latin-script (hi-Latn) train doc
Pairs between CONTAM_REJECT_MIN and the threshold are logged as rejected candidates.
"""
from collections import Counter, defaultdict
from . import config as C
from .normalize import tokens
from .translit import skeleton

PRIORITY = {"exact": 0, "normalized": 1, "near": 2, "cross_script": 3}


def _grams(toks, n):
    if len(toks) < n:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def _is_devanagari(text):
    dev = sum(1 for ch in text if "\u0900" <= ch <= "\u097f")
    return dev >= 0.5 * max(1, sum(1 for ch in text if ch.isalpha()))


class Detector:
    def __init__(self, eval_items):
        self.items = eval_items
        self.gram_index = defaultdict(list)
        self.eval_grams, self.compact, self.xs_sets = [], [], {}
        self.xs_index = defaultdict(list)
        for i, it in enumerate(eval_items):
            toks = tokens(it["text"])
            g = _grams(toks, C.CONTAM_NGRAM)
            self.eval_grams.append(g)
            self.compact.append("".join(toks))
            for x in g:
                self.gram_index[x].append(i)
            if _is_devanagari(it["text"]):
                sk = skeleton(it["text"])
                if len(sk) >= C.XS_MIN_SKELETON:
                    sh = {sk[j:j + C.XS_K] for j in range(len(sk) - C.XS_K + 1)}
                    self.xs_sets[i] = sh
                    for x in sh:
                        self.xs_index[x].append(i)

    def check(self, doc):
        """-> (matches, rejected); matches = {eval_idx: (method, score)}"""
        text = doc["text"]
        toks = tokens(text)
        hits = Counter()
        for g in _grams(toks, C.CONTAM_NGRAM):
            for i in self.gram_index.get(g, ()):
                hits[i] += 1
        matches, rejected = {}, []
        compact = None
        for i, h in sorted(hits.items()):
            score = h / max(1, len(self.eval_grams[i]))
            if score < C.CONTAM_REJECT_MIN:
                continue
            if self.items[i]["text"] in text:
                matches[i] = ("exact", 1.0)
                continue
            if compact is None:
                compact = "".join(toks)
            if self.compact[i] and self.compact[i] in compact:
                matches[i] = ("normalized", 1.0)
            elif score >= C.CONTAM_NEAR:
                matches[i] = ("near", round(score, 3))
            else:
                rejected.append((i, "near", round(score, 3)))
        if self.xs_sets and doc["lang"] == "hi-Latn":
            sk = skeleton(text)
            tally = Counter()
            seen = set()
            for j in range(len(sk) - C.XS_K + 1):
                x = sk[j:j + C.XS_K]
                if x in seen:
                    continue
                seen.add(x)
                for i in self.xs_index.get(x, ()):
                    tally[i] += 1
            for i, h in sorted(tally.items()):
                score = h / len(self.xs_sets[i])
                if i in matches:
                    continue
                if score >= C.XS_THRESHOLD:
                    matches[i] = ("cross_script", round(score, 3))
                elif score >= C.CONTAM_REJECT_MIN:
                    rejected.append((i, "cross_script", round(score, 3)))
        return matches, rejected
