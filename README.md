# Indic (Hindi + Hinglish) training-corpus pipeline

    ./download.sh data/raw          # network; the ONLY step that needs internet
    ./run.sh data/raw out           # offline, streaming, deterministic, restartable

Outputs in `out/`: `clean/part-*.jsonl.gz` (id,text,lang,source), `ledger.jsonl`, `eval.jsonl`,
`contamination.jsonl` (+ `contamination_rejected.jsonl`), `manifest.json`. `out/_work/` is resume state (safe to delete).

## Pipeline (src/)
| file | job |
|---|---|
| reader.py | streaming readers (MediaWiki XML, jsonl, csv/tsv, parquet, txt; .gz/.bz2/.xz); malformed -> counted records |
| normalize.py | NFC, invisible chars (incl. ZWJ/ZWNJ), whitespace; comparison tokens |
| langid.py | `hi` / `hi-Latn` / `en` / `other` (script share + romanised-Hindi word list) |
| filters.py | markup, mojibake, spam, repetition, boilerplate (no blanket min-length) |
| pii.py | `<PHONE> <EMAIL> <AADHAAR> <PAN>`, Devanagari digits, Verhoeff check for plain 12-digit Aadhaar |
| dedup.py | exact hash + MinHash/LSH near-dup (numpy, seeded) |
| contamination.py | exact / normalized / near / cross-script (consonant skeleton) leak detection |
| pipeline.py | orchestration: sharded stage A (resumable) + global stage B, atomic publish |

## Design rules that make it safe to kill and rerun
* Stage A writes each 5,000-record shard to `.tmp`, renames it, and writes `.done` last. A restarted run skips finished shards.
* Stage B is a pure function of the shards and is re-run from scratch; outputs are built in temp files and swapped in; `manifest.json` is written last.
* gzip is written with mtime=0; no Python `hash()`; all randomness is seeded; ordering is by (sorted file path, record order).
* `tests/test_e2e.py` proves it: two clean runs are byte-identical, and a run killed after shard 2 then resumed equals an uninterrupted run.

## Tools (for DECISIONS.md)
    python tools/dedup_review.py out > dedup_review.txt     # read pairs, pick NEAR_THRESHOLD, save 3 near-threshold pairs
    python tools/langid_check.py sample data/raw 100 labels.csv   # label 'true' column by hand
    python tools/langid_check.py score labels.csv                 # accuracy for DECISIONS.md
    python tools/make_sample.py out/clean sample_1000.jsonl

## Tests
    pip install -r requirements.txt && python -m pytest -q
