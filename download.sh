#!/usr/bin/env bash
# Network access lives ONLY in this script.   Usage: ./download.sh [raw_dir=data/raw]
# Raw files are stored exactly as downloaded; sha256 of each is written next to it.
set -euo pipefail
cd "$(dirname "$0")"
RAW="${1:-data/raw}"
mkdir -p "$RAW"
LIC_WIKI="CC BY-SA 4.0 + GFDL (Wikimedia text; see https://dumps.wikimedia.org/legal.html)"

wiki() {  # <source_dir> <dump_name> <human_name>
  local d="$RAW/$1"; mkdir -p "$d"
  local f="$d/$2-latest-pages-articles.xml.bz2"
  [ -s "$f" ] || curl -L --fail --retry 3 -C - -o "$f" "https://dumps.wikimedia.org/$2/latest/$2-latest-pages-articles.xml.bz2"
  sha256sum "$f" > "$f.sha256"
  python3 tools/record_source.py "$RAW" "$3" "https://dumps.wikimedia.org/$2/latest/" "$LIC_WIKI"
}

# --- Hindi (Devanagari): three Wikimedia projects, XML dumps ---
wiki hiwiki       hiwiki       "Hindi Wikipedia"
wiki hiwikisource hiwikisource "Hindi Wikisource"
wiki hiwikiquote  hiwikiquote  "Hindi Wikiquote"       # short quotes/proverbs: good filter stress test

# --- Hinglish (Latin-script Hindi): Hugging Face dataset(s). TRY IN ORDER, KEEP WHAT WORKS. ---
# I could not verify these repos or their licenses from here: check each dataset card yourself.
# Override with:  HINGLISH_REPOS="owner/name another/name" ./download.sh
REPOS="${HINGLISH_REPOS:-Abhishekcr448/Hinglish-Everyday-Conversations-1M findnitai/english-to-hinglish}"
for r in $REPOS; do
  d="$RAW/hinglish_$(echo "$r" | tr '/' '_')"
  if python3 tools/hf_download.py "$r" "$d" "$RAW"; then
    find "$d" -type f ! -path '*/.*' ! -name '*.sha256' -exec sha256sum {} \; > "$d/files.sha256" || true
  else
    echo "WARN: could not download $r -> write this down in DECISIONS.md" >&2
  fi
done
echo "Done. Next: check the license of every entry in $RAW/SOURCES.json, then ./run.sh $RAW out"
