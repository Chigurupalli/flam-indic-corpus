"""1,000-row deterministic random sample of cleaned output (reservoir, seed 0).
    python tools/make_sample.py <out_dir>/clean sample_1000.jsonl"""
import gzip, json, os, random, sys
d, dest = sys.argv[1], sys.argv[2]
rng, res, n = random.Random(0), [], 0
for f in sorted(os.listdir(d)):
    for line in gzip.open(os.path.join(d, f), "rt", encoding="utf-8"):
        n += 1
        if len(res) < 1000:
            res.append(line)
        else:
            j = rng.randint(0, n - 1)
            if j < 1000:
                res[j] = line
with open(dest, "w", encoding="utf-8") as o:
    o.writelines(res)
print(f"sampled {len(res)} of {n}")
