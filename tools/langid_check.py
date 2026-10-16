"""Measure langid accuracy on YOUR hand labels.
    python tools/langid_check.py sample <raw_dir> 100 labels.csv   # writes csv with empty 'true' column
    (open labels.csv, fill 'true' with one of hi / hi-Latn / en / other, save)
    python tools/langid_check.py score labels.csv                  # accuracy + confusion matrix
Samples are drawn from the RAW input (so English/other docs are included), by hash of doc id."""
import csv, hashlib, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.langid import detect
from src.normalize import normalize
from src.reader import iter_records


def sample(raw, n, out):
    keep = []
    for k, rec in enumerate(iter_records(raw)):
        if rec.error or not rec.text:
            continue
        t = normalize(rec.text)
        if t:
            keep.append((hashlib.sha1(rec.id.encode()).hexdigest(), rec.id, rec.source, t))
        if k > 200000:
            break
    keep.sort()
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "source", "predicted", "true", "text"])
        for _, i, s, t in keep[:n]:
            w.writerow([i, s, detect(t), "", t[:300].replace("\n", " ")])


def score(path):
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["true"].strip()]
    conf = Counter((r["true"].strip(), r["predicted"]) for r in rows)
    ok = sum(v for (t, p), v in conf.items() if t == p)
    print(f"labelled={len(rows)} accuracy={ok/max(1,len(rows)):.3f}")
    for (t, p), v in sorted(conf.items()):
        print(f"  true={t:8s} pred={p:8s} n={v}")


if sys.argv[1] == "sample":
    sample(sys.argv[2], int(sys.argv[3]), sys.argv[4])
else:
    score(sys.argv[2])
