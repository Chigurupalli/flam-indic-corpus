"""Streaming readers. Yields one Record per input document, in a deterministic order
(files sorted by relative path, records in file order). Malformed records are NOT
raised: they come out as Records with `error` set, so the ledger counts them.

Supported: MediaWiki XML dumps (.xml), JSON Lines (.jsonl/.ndjson), CSV/TSV, parquet,
plain text (one document per non-empty line); each optionally .gz/.bz2/.xz.
Source name = first directory under raw_dir (or the file stem for top-level files).
Optional raw_dir/READER_CONFIG.json: {"<source>": {"text_field": "<column>"}}.
"""
import bz2, csv, gzip, hashlib, html, io, json, lzma, os, re, sys, zlib
import xml.etree.ElementTree as ET
from collections import namedtuple

Record = namedtuple("Record", "id source relpath ordinal text error")

TEXT_FIELDS = ("text", "content", "body", "document", "article", "hinglish", "hindi",
               "sentence", "sentences", "raw_text", "review", "message", "tweet",
               "comment", "description", "title")
SKIP_NAMES = {"SOURCES.json", "READER_CONFIG.json"}
SKIP_SUFFIX = (".sha256", ".sha256sum", ".md", ".lock", ".metadata", ".log", ".txt.sha256")
COMPRESSION = (".gz", ".bz2", ".xz")
csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))


def doc_id(source, relpath, ordinal):
    return hashlib.sha1(f"{source}|{relpath}|{ordinal}".encode("utf-8")).hexdigest()[:16]


def _open(path):
    p = path.lower()
    if p.endswith(".gz"):
        return gzip.open(path, "rb")
    if p.endswith(".bz2"):
        return bz2.open(path, "rb")
    if p.endswith(".xz"):
        return lzma.open(path, "rb")
    return open(path, "rb")


def _ext(path):
    p = path.lower()
    for c in COMPRESSION:
        if p.endswith(c):
            p = p[: -len(c)]
    return os.path.splitext(p)[1]


def pick_field(row, forced=None):
    if forced and isinstance(row.get(forced), str):
        return forced
    low = {k.lower(): k for k in row if isinstance(k, str)}
    for f in TEXT_FIELDS:
        k = low.get(f)
        if k is not None and isinstance(row[k], str):
            return k
    strs = [(len(v), k) for k, v in row.items() if isinstance(v, str)]
    return max(strs)[1] if strs else None


# ---------------- wikitext -> plain text ----------------
_NS = r"file|image|category|media|चित्र|श्रेणी|फ़ाइल|फाइल|वर्ग|कैटेगरी"
_R = {
    "comment": re.compile(r"<!--.*?-->", re.S),
    "ref": re.compile(r"<ref[^>/]*?>.*?</ref>|<ref[^>]*/>", re.S | re.I),
    "dropblock": re.compile(r"<(gallery|math|timeline|imagemap|syntaxhighlight|code|pre|nowiki)\b[^>]*>.*?</\1>", re.S | re.I),
    "tpl": re.compile(r"\{\{[^{}]*\}\}"),
    "table": re.compile(r"\{\|(?:(?!\{\|).)*?\|\}", re.S),
    "link": re.compile(rf"\[\[(?!(?:{_NS})\s*:)(?:[^\[\]|]*\|)?([^\[\]]*)\]\]", re.I),
    "filelink": re.compile(rf"\[\[(?:{_NS})\s*:[^\[\]]*\]\]", re.I),
    "extlink": re.compile(r"\[(?:https?:)?//[^\s\]]+\s+([^\]]*)\]"),
    "bareext": re.compile(r"\[(?:https?:)?//[^\s\]]+\]"),
    "quotes": re.compile(r"'{2,5}"),
    "heading": re.compile(r"^=+\s*(.*?)\s*=+\s*$", re.M),
    "listmark": re.compile(r"^[*#:;]+\s*", re.M),
    "magic": re.compile(r"__\w+__"),
    "tag": re.compile(r"<[^>]+>"),
    "interlang": re.compile(r"^[a-z]{2,3}(?:-[a-z]+)?:\S.*$", re.M),
}


def wikitext_to_text(w: str) -> str:
    w = _R["comment"].sub("", w)
    w = _R["ref"].sub("", w)
    w = _R["dropblock"].sub("", w)
    for _ in range(8):
        n = _R["tpl"].sub("", w)
        if n == w:
            break
        w = n
    for _ in range(4):
        n = _R["table"].sub("", w)
        if n == w:
            break
        w = n
    for _ in range(3):
        w = _R["link"].sub(r"\1", w)
    w = _R["filelink"].sub("", w)
    w = _R["extlink"].sub(r"\1", w)
    w = _R["bareext"].sub("", w)
    w = _R["quotes"].sub("", w)
    w = _R["heading"].sub(r"\1", w)
    w = _R["listmark"].sub("", w)
    w = _R["magic"].sub("", w)
    w = _R["tag"].sub("", w)
    w = _R["interlang"].sub("", w)
    return html.unescape(w)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


# ---------------- per-format iterators: yield (text|None, error|None) ----------------
def _iter_mediawiki(fh):
    root = None
    try:
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            if root is None:
                root = el
                continue
            if ev != "end" or _local(el.tag) != "page":
                continue
            info, redirect = {}, False
            for ch in el.iter():
                name = _local(ch.tag)
                if name in ("ns", "title", "text") and name not in info:
                    info[name] = ch.text
                elif name == "redirect":
                    redirect = True
            el.clear()
            root.clear()
            if redirect:
                yield None, "redirect"
            elif (info.get("ns") or "0").strip() != "0":
                yield None, f"namespace:{(info.get('ns') or '?').strip()}"
            else:
                yield wikitext_to_text(info.get("text") or ""), None
    except ET.ParseError as e:
        yield None, "xml_parse_error"


def _iter_jsonl(fh, forced):
    for raw in fh:
        if not raw.strip():
            continue
        try:
            line = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            yield None, "bad_utf8"
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            yield None, "bad_json"
            continue
        if isinstance(obj, str):
            yield obj, None
        elif isinstance(obj, dict):
            k = pick_field(obj, forced)
            yield (obj[k], None) if k else (None, "no_text_field")
        else:
            yield None, "not_object"


def _iter_csv(fh, forced, delim):
    wrapper = io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace", newline="")
    reader = csv.DictReader(wrapper, delimiter=delim)
    errors = 0
    while True:
        try:
            row = next(reader)
        except StopIteration:
            return
        except csv.Error:
            errors += 1
            yield None, "bad_csv_row"
            if errors > 1000:
                return
            continue
        k = pick_field(row, forced)
        yield (row[k], None) if k else (None, "no_text_field")


def _iter_txt(fh):
    for raw in fh:
        if not raw.strip():
            continue
        try:
            yield raw.decode("utf-8-sig"), None
        except UnicodeDecodeError:
            yield None, "bad_utf8"


def _iter_parquet(path, forced):
    try:
        import pyarrow.parquet as pq
    except ImportError:
        yield None, "pyarrow_missing"
        return
    try:
        pf = pq.ParquetFile(path)
        field = None
        for batch in pf.iter_batches(batch_size=1000):
            for row in batch.to_pylist():
                if field is None:
                    field = pick_field(row, forced)
                yield (row.get(field), None) if field else (None, "no_text_field")
    except Exception:
        yield None, "parquet_read_error"


def _iter_file(path, ext, forced):
    if ext == ".parquet":
        yield from _iter_parquet(path, forced)
        return
    with _open(path) as fh:
        if ext == ".xml":
            yield from _iter_mediawiki(fh)
        elif ext in (".jsonl", ".ndjson"):
            yield from _iter_jsonl(fh, forced)
        elif ext in (".csv", ".tsv"):
            yield from _iter_csv(fh, forced, "\t" if ext == ".tsv" else ",")
        elif ext == ".txt":
            yield from _iter_txt(fh)
        else:
            yield None, f"unsupported_format:{ext or 'none'}"


def list_files(raw_dir):
    out = []
    for base, dirs, files in os.walk(raw_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for f in sorted(files):
            if f.startswith(".") or f in SKIP_NAMES or f.lower().endswith(SKIP_SUFFIX):
                continue
            out.append(os.path.relpath(os.path.join(base, f), raw_dir))
    return sorted(out)


def source_of(relpath):
    parts = relpath.split(os.sep)
    if len(parts) > 1:
        return parts[0]
    name = parts[0]
    for c in COMPRESSION:
        if name.lower().endswith(c):
            name = name[: -len(c)]
    return os.path.splitext(name)[0]


def iter_records(raw_dir):
    cfg_path = os.path.join(raw_dir, "READER_CONFIG.json")
    cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
    for rel in list_files(raw_dir):
        source = source_of(rel)
        forced = cfg.get(source, {}).get("text_field")
        ext = _ext(rel)
        ordinal = 0
        try:
            for text, err in _iter_file(os.path.join(raw_dir, rel), ext, forced):
                if err is None and not isinstance(text, str):
                    text, err = None, "text_not_string"
                yield Record(doc_id(source, rel, ordinal), source, rel, ordinal, text, err)
                ordinal += 1
        except (EOFError, OSError, zlib.error, lzma.LZMAError):
            yield Record(doc_id(source, rel, ordinal), source, rel, ordinal, None, "truncated_or_corrupt_file")
