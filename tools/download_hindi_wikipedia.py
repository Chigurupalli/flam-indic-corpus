import json
from pathlib import Path
from datasets import load_dataset

out = Path("data/raw/hindi_wikipedia")
out.mkdir(parents=True, exist_ok=True)
target = out / "articles.jsonl"

ds = load_dataset(
    "wikimedia/wikipedia",
    "20231101.hi",
    split="train",
    streaming=True,
)

count = 0

with target.open("w", encoding="utf-8") as f:
    for row in ds:
        text = row.get("text", "")
        if not isinstance(text, str) or not text.strip():
            continue

        # Preserve the source fields and original text.
        record = {
            "id": row.get("id"),
            "title": row.get("title"),
            "url": row.get("url"),
            "text": text,
            "source": "wikimedia/wikipedia:20231101.hi",
        }
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        count += 1

        if count >= 15000:
            break

print(f"Saved {count} source records to {target}")
