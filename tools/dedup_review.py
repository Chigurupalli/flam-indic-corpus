"""Pick the near-dup threshold by LOOKING at pairs.   Usage:
    python tools/dedup_review.py <out_dir> [max_docs=30000] > dedup_review.txt
Runs after one pipeline run (uses out_dir/_work stage-A survivors). It finds candidate pairs with a
LOOSE LSH (32 bands x 4 rows), computes EXACT Jaccard of character shingles, buckets pairs by Jaccard
and prints 8 random pairs per bucket. Read them, find the bucket where pairs flip from 'same doc' to
'just similar', set NEAR_THRESHOLD in src/config.py, and save 3 pairs near it for DECISIONS.md."""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import config as C
from src.dedup import NearDedup, shingle_hashes, signature
from src.io_utils import read_jsonl_gz


def main():
    out = sys.argv[1]
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else 30000
    work = os.path.join(out, "_work")
    files = sorted(f for f in os.listdir(work) if f.endswith(".docs.jsonl.gz"))
    docs = []
    for f in files:
        for d in read_jsonl_gz(os.path.join(work, f)):
            if len(d["text"]) >= C.NEAR_MIN_CHARS:
                docs.append(d)
            if len(docs) >= cap:
                break
        if len(docs) >= cap:
            break
    bands, rows = 32, 4
    tables = [dict() for _ in range(bands)]
    sets, pairs = [], set()
    for i, d in enumerate(docs):
        hs = shingle_hashes(d["text"])
        sets.append(set(hs.tolist()))
        sig = signature(hs)
        for b in range(bands):
            k = sig[b * rows:(b + 1) * rows].tobytes()
            for j in tables[b].get(k, ()):
                pairs.add((j, i))
            tables[b].setdefault(k, []).append(i)
    buckets = {}
    for i, j in pairs:
        a, b = sets[i], sets[j]
        jac = len(a & b) / len(a | b)
        if jac < 0.5:
            continue
        buckets.setdefault(min(int(jac * 10), 9), []).append((jac, i, j))
    rng = random.Random(0)
    print(f"docs={len(docs)} candidate_pairs={len(pairs)}")
    for b in sorted(buckets):
        ps = buckets[b]
        print(f"\n=========== Jaccard {b/10:.1f}-{(b+1)/10:.1f}: {len(ps)} pairs ===========")
        for jac, i, j in rng.sample(ps, min(8, len(ps))):
            print(f"--- J={jac:.3f}  {docs[i]['id']} vs {docs[j]['id']}")
            print("A:", docs[i]["text"][:250].replace("\n", " "))
            print("B:", docs[j]["text"][:250].replace("\n", " "))


main()
