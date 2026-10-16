"""Download a Hugging Face dataset repo AS-IS (no transformation) and record its license.
    python tools/hf_download.py <repo_id> <dest_dir> <raw_dir>
License is read from the dataset card metadata; READ THE CARD YOURSELF as well."""
import json, os, sys, datetime
from huggingface_hub import HfApi, snapshot_download

repo, dest, raw = sys.argv[1:4]
info = HfApi().dataset_info(repo)
lic = getattr(info.card_data, "license", None) if info.card_data else None
if getattr(info, "gated", False):
    sys.exit(f"{repo} is gated - skipping (not freely usable)")
snapshot_download(repo_id=repo, repo_type="dataset", local_dir=dest,
                  allow_patterns=["*.parquet", "*.csv", "*.tsv", "*.json", "*.jsonl", "*.jsonl.gz", "*.txt", "*.md"])
entry = {"name": repo, "url": f"https://huggingface.co/datasets/{repo}", "license": lic or "UNKNOWN - check card",
         "downloaded": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"), "revision": info.sha}
path = os.path.join(raw, "SOURCES.json")
cur = json.load(open(path)) if os.path.exists(path) else []
cur = [c for c in cur if c["name"] != repo] + [entry]
json.dump(cur, open(path, "w"), indent=2, ensure_ascii=False)
print("recorded", entry)
