"""All tunable thresholds live here, so manifest.json can record them and
DECISIONS.md can cite them. Change a value -> the pipeline fingerprint changes
-> stale resume state is discarded automatically."""
import os

# --- sharding / resume ---
SHARD_SIZE = int(os.environ.get("FLAM_SHARD_SIZE", 5000))   # input records per shard

# --- language id ---
KEEP_LANGS = ("hi", "hi-Latn")   # corpus is Hindi/Hinglish; en/other are labelled then dropped
DEVANAGARI_MIN = 0.5             # share of letters that must be Devanagari for "hi"
LATIN_MIN = 0.5                  # share of letters that must be Latin to try hi-Latn vs en
HINGLISH_MIN_RATIO = 0.10        # romanised-Hindi function words / tokens
HINGLISH_MIN_HITS = 2
MIN_TOKENS_LATIN = 3             # Latin text shorter than this is too ambiguous to label

# --- quality filters ---
MAX_HTML_TAGS = 2
MAX_WIKI_MARKERS = 3
MAX_REPLACEMENT_CHARS = 2
MAX_URL_SHARE = 0.30
MAX_PHONES_IN_DOC = 5
REPEAT_MIN_TOKENS = 10
REPEAT_TOP_SHARE = 0.40
REPEAT_UNIQUE_RATIO = 0.15
SYMBOL_RATIO_MAX = 0.25
MARKUP_RESIDUE_MAX = 0.20
BOILERPLATE_LINE_SHARE = 0.5
BOILERPLATE_LINE_MAXLEN = 120

# --- near-duplicate detection (MinHash + LSH) ---
NUM_PERM = 128
BANDS = 16
ROWS = 8                         # BANDS * ROWS must equal NUM_PERM
SHINGLE = 5                      # character shingle size
NEAR_THRESHOLD = 0.80            # estimated Jaccard; chosen with tools/dedup_review.py
NEAR_MIN_CHARS = 30              # shorter docs: exact-dedup only (proverbs differ by 1 word)
MAX_SHINGLES = 20000
MINHASH_SEED = 1

# --- eval set ---
EVAL_SIZE = 200
EVAL_HINGLISH = 60
EVAL_SEED = "flam-eval-v1"
EVAL_MIN_CHARS = 40
EVAL_MAX_CHARS = 500
EVAL_MIN_TOKENS = 8

# --- contamination ---
CONTAM_NGRAM = 4                 # word n-gram for exact/normalized/near
CONTAM_NEAR = 0.60               # containment of eval n-grams inside a train doc
CONTAM_REJECT_MIN = 0.30         # below NEAR but logged as "rejected candidate"
XS_K = 7                         # skeleton char shingle for cross-script
XS_THRESHOLD = 0.60
XS_MIN_SKELETON = 20


def as_dict():
    return {k: v for k, v in globals().items() if k.isupper()}
