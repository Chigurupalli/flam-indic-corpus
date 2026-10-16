"""Orchestrator:  python -m src.pipeline <raw_dir> <out_dir>

Stage A (per record, sharded, resumable):  read -> normalize -> langid -> filter -> PII redact
   Each shard of SHARD_SIZE input records is written atomically (tmp + os.replace) and marked
   complete by a .done file written LAST. A restarted run skips completed shards.
Stage B (global, deterministic, re-run from scratch every time; ~cheap vs A):
   eval holdout -> contamination removal -> exact+near dedup -> write outputs atomically.
"""
import hashlib, heapq, json, os, re, shutil, subprocess, sys, platform
from collections import Counter, defaultdict
from . import config as C
from .contamination import Detector, PRIORITY
from .dedup import NearDedup, exact_key
from .filters import garbled_reason, quality_reason
from .io_utils import atomic_write_text, dumps, read_jsonl_gz, sha256_file, write_jsonl_gz
from .langid import detect
from .normalize import normalize, tokens
from .pii import redact
from .reader import iter_records, list_files

STAGES = ["read", "normalize", "langid", "filter", "holdout", "contamination", "dedup"]
CLEAN_PART_ROWS = 50000
PLACEHOLDER = re.compile(r"<(?:PHONE|EMAIL|AADHAAR|PAN)>")


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- Stage A
def process_record(rec, pii_total):
    row = {"id": rec.id, "source": rec.source, "lang": None,
           "status": "dropped", "stage": "", "reason": "", "dup_of": None}
    if rec.error:
        row.update(stage="read", reason=rec.error)
        return row, None
    text = normalize(rec.text)
    if not text:
        row.update(stage="normalize", reason="empty_after_normalize")
        return row, None
    bad = garbled_reason(text)
    if bad:
        row.update(stage="filter", reason=bad)
        return row, None
    lang = detect(text)
    row["lang"] = lang
    if lang not in C.KEEP_LANGS:
        row.update(stage="langid", reason=f"not_hindi:{lang}")
        return row, None
    why = quality_reason(text, lang)
    if why:
        row.update(stage="filter", reason=why)
        return row, None
    text, counts = redact(text)
    pii_total.update(counts)
    row.update(status="pending")
    return row, {"id": rec.id, "source": rec.source, "lang": lang, "text": text}


def fingerprint(raw_dir):
    files = [(f, os.path.getsize(os.path.join(raw_dir, f))) for f in list_files(raw_dir)]
    blob = json.dumps({"config": C.as_dict(), "files": files}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def run_stage_a(raw_dir, work):
    crash_after = os.environ.get("FLAM_CRASH_AFTER_SHARD")   # test hook only
    buf, idx, skipped, done = [], 0, 0, 0

    def flush(idx, buf):
        nonlocal skipped, done
        base = os.path.join(work, f"a-{idx:06d}")
        if os.path.exists(base + ".done"):
            skipped += 1
            return
        pii = Counter()
        rows, docs = [], []
        for rec in buf:
            r, d = process_record(rec, pii)
            rows.append(r)
            if d:
                docs.append(d)
        write_jsonl_gz(base + ".ledger.jsonl.gz", rows)
        write_jsonl_gz(base + ".docs.jsonl.gz", docs)
        atomic_write_text(base + ".done", json.dumps({"records": len(rows), "pii": dict(pii)}))
        done += 1
        if crash_after is not None and idx == int(crash_after):
            log(f"[test hook] simulated kill after shard {idx}")
            os._exit(137)

    for rec in iter_records(raw_dir):
        buf.append(rec)
        if len(buf) == C.SHARD_SIZE:
            flush(idx, buf)
            idx += 1
            buf = []
    if buf:
        flush(idx, buf)
        idx += 1
    log(f"stage A: {idx} shards ({done} processed, {skipped} resumed from previous run)")
    return idx


def shard_paths(work, suffix):
    return sorted(os.path.join(work, f) for f in os.listdir(work) if f.endswith(suffix))


def iter_docs(work):
    for p in shard_paths(work, ".docs.jsonl.gz"):
        yield from read_jsonl_gz(p)


# ---------------------------------------------------------------- Stage B
def extract_passage(text):
    """First paragraph/sentence of reasonable length, used as the eval item."""
    for para in text.split("\n"):
        cands = [para] if len(para) <= C.EVAL_MAX_CHARS else re.split(r"(?<=[।.?!])\s+", para)
        for s in cands:
            s = s.strip()
            if (C.EVAL_MIN_CHARS <= len(s) <= C.EVAL_MAX_CHARS and len(tokens(s)) >= C.EVAL_MIN_TOKENS
                    and not PLACEHOLDER.search(s)):
                return s
    return None


def _score(doc_id):
    return int(hashlib.sha256(f"{C.EVAL_SEED}|{doc_id}".encode()).hexdigest()[:15], 16)


def select_eval(work):
    """Hold out by hash(id): deterministic, independent of input order or file size."""
    cap = {"hi": 3 * C.EVAL_SIZE, "hi-Latn": 3 * C.EVAL_HINGLISH}
    heaps = {"hi": [], "hi-Latn": []}
    for d in iter_docs(work):
        p = extract_passage(d["text"])
        if not p:
            continue
        h, s = heaps[d["lang"]], _score(d["id"])
        item = (-s, d["id"], p, d["source"])
        if len(h) < cap[d["lang"]]:
            heapq.heappush(h, item)
        elif s < -h[0][0]:
            heapq.heapreplace(h, item)

    def ranked(lang):
        seen, out = set(), []
        for ns, did, p, src in sorted(heaps[lang], key=lambda x: (-x[0], x[1])):
            key = "".join(tokens(p))
            if key in seen:
                continue
            seen.add(key)
            out.append((-ns, did, p, src, lang))
        return out

    hl, hi = ranked("hi-Latn"), ranked("hi")
    n_hl = min(C.EVAL_HINGLISH, len(hl))
    n_hi = min(C.EVAL_SIZE - n_hl, len(hi))
    chosen = hl[:n_hl] + hi[:n_hi]
    if len(chosen) < C.EVAL_SIZE:
        chosen += hl[n_hl:n_hl + (C.EVAL_SIZE - len(chosen))]
    chosen.sort()
    return [{"eval_id": f"e{i:04d}", "text": p, "lang": lang, "source": src, "doc_id": did}
            for i, (s, did, p, src, lang) in enumerate(chosen)]


def run_stage_b(work, out_dir):
    late = {}   # doc_id -> (stage, reason, dup_of)

    # 1. eval holdout
    eval_items = select_eval(work)
    held = {e["doc_id"]: e["eval_id"] for e in eval_items}
    for did, eid in held.items():
        late[did] = ("holdout", f"eval_item:{eid}", None)
    log(f"eval: {len(eval_items)} items ({sum(e['lang']=='hi-Latn' for e in eval_items)} hi-Latn)")

    # 2. contamination
    det = Detector(eval_items)
    per_eval = defaultdict(lambda: defaultdict(list))
    rejected_rows, leak_ids = [], set()
    for d in iter_docs(work):
        if d["id"] in held:
            continue
        matches, rejected = det.check(d)
        for i, (method, score) in matches.items():
            per_eval[eval_items[i]["eval_id"]][method].append(d["id"])
            leak_ids.add(d["id"])
        for i, method, score in rejected:
            if len(rejected_rows) < 500:
                rejected_rows.append({"eval_id": eval_items[i]["eval_id"], "train_id": d["id"],
                                      "method": method, "score": score,
                                      "eval_text": eval_items[i]["text"][:200], "train_text": d["text"][:200]})
    doc_methods = defaultdict(list)
    for eid, bym in per_eval.items():
        for m, ids in bym.items():
            for t in ids:
                doc_methods[t].append(m)
    for t in leak_ids:
        best = min(doc_methods[t], key=PRIORITY.get)
        late[t] = ("contamination", f"leak:{best}", None)
    contam_rows = []
    for eid in sorted(per_eval):
        bym = {m: sorted(set(v)) for m, v in per_eval[eid].items()}
        method = min(bym, key=PRIORITY.get)
        contam_rows.append({"eval_id": eid, "train_ids": sorted({t for v in bym.values() for t in v}),
                            "method": method, "by_method": bym})
    log(f"contamination: {len(contam_rows)} eval items affected, {len(leak_ids)} train docs removed")

    # 3. dedup + write clean parts
    tmp_clean = os.path.join(out_dir, "clean.tmp")
    shutil.rmtree(tmp_clean, ignore_errors=True)
    os.makedirs(tmp_clean)
    exact_seen, near = {}, NearDedup()
    part, part_rows, part_no = [], 0, 0
    clean_hashes = []

    def flush_part():
        nonlocal part, part_no
        if part:
            p = os.path.join(tmp_clean, f"part-{part_no:05d}.jsonl.gz")
            write_jsonl_gz(p, part)
            part_no += 1
            part = []

    for d in iter_docs(work):
        did = d["id"]
        if did in late:
            continue
        k = exact_key(d["text"])
        if k in exact_seen:
            late[did] = ("dedup", "exact_duplicate", exact_seen[k])
            continue
        if len(d["text"]) >= C.NEAR_MIN_CHARS:
            canon, sim = near.query_add(did, d["text"])
            if canon:
                late[did] = ("dedup", f"near_duplicate:{sim:.3f}", canon)
                continue
        exact_seen[k] = did
        part.append({"id": did, "text": d["text"], "lang": d["lang"], "source": d["source"]})
        if len(part) >= CLEAN_PART_ROWS:
            flush_part()
    flush_part()
    return eval_items, contam_rows, rejected_rows, late, tmp_clean


def publish(raw_dir, out_dir, work, eval_items, contam_rows, rejected_rows, late, tmp_clean, pii_total):
    # ledger (streamed) + funnel
    tmp_ledger = os.path.join(out_dir, "ledger.jsonl.tmp")
    stage_idx = {s: i for i, s in enumerate(STAGES)}
    dropped = defaultdict(Counter)   # stage -> lang -> n
    reasons = defaultdict(Counter)
    kept = Counter()
    total = 0
    labeled = Counter()
    final_stage = []                 # (lang, stage_index or None)
    with open(tmp_ledger, "w", encoding="utf-8", newline="\n") as lf:
        for p in shard_paths(work, ".ledger.jsonl.gz"):
            for row in read_jsonl_gz(p):
                total += 1
                if row["status"] == "pending":
                    if row["id"] in late:
                        st, why, dup = late[row["id"]]
                        row.update(status="dropped", stage=st, reason=why, dup_of=dup)
                    else:
                        row.update(status="kept", stage="output", reason="", dup_of=None)
                lf.write(dumps({k: row[k] for k in ("id", "status", "stage", "reason", "dup_of", "source", "lang")}) + "\n")
                lang = row["lang"] or "unlabeled"
                if row["lang"]:
                    labeled[lang] += 1
                if row["status"] == "kept":
                    kept[lang] += 1
                    final_stage.append((lang, None))
                else:
                    dropped[row["stage"]][lang] += 1
                    reasons[row["stage"]][row["reason"].split(":")[0] if row["stage"] != "dedup" else row["reason"].split(":")[0]] += 1
                    final_stage.append((lang, stage_idx[row["stage"]]))
    per_lang = {}
    for lang in sorted(labeled):
        c = {"labeled": labeled[lang]}
        for st in ["langid", "filter", "holdout", "contamination", "dedup"]:
            si = stage_idx[st]
            c[f"after_{st}"] = sum(1 for l, s in final_stage if l == lang and (s is None or s > si))
        per_lang[lang] = c
    funnel = {
        "input_records": total,
        "dropped_by_stage": {s: dict(dropped[s]) for s in STAGES if s in dropped},
        "drop_reasons": {s: dict(reasons[s]) for s in STAGES if s in reasons},
        "per_language": per_lang,
        "final_kept": dict(kept),
    }

    # eval / contamination files
    atomic_write_text(os.path.join(out_dir, "eval.jsonl"), "".join(dumps(e) + "\n" for e in eval_items))
    atomic_write_text(os.path.join(out_dir, "contamination.jsonl"), "".join(dumps(r) + "\n" for r in contam_rows))
    atomic_write_text(os.path.join(out_dir, "contamination_rejected.jsonl"), "".join(dumps(r) + "\n" for r in rejected_rows))

    # manifest
    rel_files = list_files(raw_dir)
    src_meta = os.path.join(raw_dir, "SOURCES.json")
    manifest = {
        "sources": json.load(open(src_meta, encoding="utf-8")) if os.path.exists(src_meta) else [],
        "input_files": [{"path": f, "bytes": os.path.getsize(os.path.join(raw_dir, f)),
                         "sha256": sha256_file(os.path.join(raw_dir, f))} for f in rel_files],
        "thresholds": C.as_dict(),
        "counts": funnel,
        "pii_redactions": dict(pii_total),
        "eval": {"items": len(eval_items), "affected_by_leak": len(contam_rows)},
        "environment": {"python": platform.python_version(), "git_commit": _git_commit()},
    }
    # swap clean/ in, then ledger, then manifest (manifest last: its presence = run complete)
    final_clean = os.path.join(out_dir, "clean")
    shutil.rmtree(final_clean, ignore_errors=True)
    os.replace(tmp_clean, final_clean)
    os.replace(tmp_ledger, os.path.join(out_dir, "ledger.jsonl"))
    manifest["output_hashes"] = {n: sha256_file(os.path.join(final_clean, n)) for n in sorted(os.listdir(final_clean))}
    manifest["output_hashes"]["eval.jsonl"] = sha256_file(os.path.join(out_dir, "eval.jsonl"))
    atomic_write_text(os.path.join(out_dir, "manifest.json"), json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    log(f"done: {total} input, {sum(kept.values())} kept {dict(kept)}")


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL,
                                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).decode().strip()
    except Exception:
        return None


def main(argv):
    if len(argv) != 2:
        sys.exit("usage: run.sh <raw_dir> <out_dir>")
    raw_dir, out_dir = argv
    if not os.path.isdir(raw_dir):
        sys.exit(f"raw_dir not found: {raw_dir}")
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(out_dir, "_work")
    fp = fingerprint(raw_dir)
    fp_file = os.path.join(work, "fingerprint")
    if os.path.isdir(work) and (not os.path.exists(fp_file) or open(fp_file).read() != fp):
        log("config/input changed since last run -> discarding stale resume state")
        shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)
    atomic_write_text(fp_file, fp)
    for f in os.listdir(work):                      # leftovers of a killed write
        if f.endswith(".tmp"):
            os.remove(os.path.join(work, f))

    run_stage_a(raw_dir, work)
    pii_total = Counter()
    for p in shard_paths(work, ".done"):
        pii_total.update(json.load(open(p))["pii"])
    res = run_stage_b(work, out_dir)
    publish(raw_dir, out_dir, work, *res, pii_total)


if __name__ == "__main__":
    main(sys.argv[1:])
