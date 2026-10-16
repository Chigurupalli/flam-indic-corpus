# Sources

This project uses two public datasets.

| Name | URL | License | Download date | Format | Input records | Approximate size |
|---|---|---|---|---|---:|---:|
| Hindi Wikipedia (`wikimedia/wikipedia`, configuration `20231101.hi`) | https://huggingface.co/datasets/wikimedia/wikipedia | CC BY-SA 3.0 and GFDL, as stated in the dataset card; individual content may have additional licensing terms | 2026-10-16 | JSONL export (`articles.jsonl`) | 15,000 | 90 MB |
| HinGE (`LingoIITGN/HinGE`) | https://huggingface.co/datasets/LingoIITGN/HinGE | CC BY 4.0 (per recorded source metadata; retain attribution) | 2026-10-16 | CSV (`HinGE.csv`) | 1,976 | 1.6 MB |

## Fields used

- Hindi Wikipedia: `text`
- HinGE: `Human-generated Hinglish`

## Raw-data preservation

The pipeline reads the files in `data/raw/`. The Hindi Wikipedia file is an exported subset in JSONL format, not the original full Wikimedia XML dump. Preserve the raw files unchanged.

## Source verification and limitations

- Wikipedia dataset card: https://huggingface.co/datasets/wikimedia/wikipedia. It identifies CC BY-SA 3.0 and GFDL; review the applicable terms and attribution requirements before redistributing derived content.
- HinGE dataset card: https://huggingface.co/datasets/LingoIITGN/HinGE. Its recorded license is CC BY 4.0; preserve appropriate attribution.
- Input record counts differ from final cleaned record counts.
- File sizes above are rounded; use exact byte counts and SHA-256 hashes recorded in the manifest for reproducibility.
- HinGE revision recorded in `data/raw/SOURCES.json`: `e25a10382d9adb77f3a4f03b721fbd0a43c0de4c`.