"""python tools/record_source.py <raw_dir> <name> <url> <license>   (appends to raw_dir/SOURCES.json)"""
import datetime, json, os, sys
raw, name, url, lic = sys.argv[1:5]
path = os.path.join(raw, "SOURCES.json")
cur = json.load(open(path)) if os.path.exists(path) else []
cur = [c for c in cur if c["name"] != name] + [{"name": name, "url": url, "license": lic,
       "downloaded": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")}]
json.dump(cur, open(path, "w"), indent=2, ensure_ascii=False)
