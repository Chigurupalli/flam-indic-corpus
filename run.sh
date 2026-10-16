
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ $# -ne 2 ]]; then
    echo "Usage: ./run.sh <raw_dir> <out_dir>" >&2
    exit 2
fi

RAW="$(cd "$1" && pwd)"
mkdir -p "$2"
OUT="$(cd "$2" && pwd)"

# Use the Python interpreter passed by the test runner.
PYTHON_BIN="${FLAM_PYTHON:-python3}"

exec "$PYTHON_BIN" -m src.pipeline "$RAW" "$OUT"
