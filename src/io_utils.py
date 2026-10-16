import gzip, hashlib, io, json, os


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


def open_gz_write(path):
    """Deterministic gzip (mtime=0, no filename) so reruns are byte-identical."""
    raw = open(path, "wb")
    gz = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    return _Closer(io.TextIOWrapper(gz, encoding="utf-8", newline="\n"), raw)


class _Closer:
    """Closes the text wrapper (flushes gzip trailer) and then the raw file."""
    def __init__(self, text, raw):
        self.text, self.raw = text, raw

    def write(self, s):
        self.text.write(s)

    def close(self):
        self.text.close()
        self.raw.close()


def write_jsonl_gz(path, rows):
    """Atomic: write to .tmp then os.replace, so a killed run never leaves a half file."""
    tmp = path + ".tmp"
    f = open_gz_write(tmp)
    try:
        for r in rows:
            f.write(dumps(r) + "\n")
    finally:
        f.close()
    os.replace(tmp, path)


def read_jsonl_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def atomic_write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def sha256_file(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(block)
            if not b:
                break
            h.update(b)
    return h.hexdigest()
