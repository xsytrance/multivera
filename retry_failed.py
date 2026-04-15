"""Retry failed characters from vera_extract.py"""
import json
import time
from pathlib import Path
from vera_extract import (
    read_docx,
    extract_character,
    hackermouth_override,
    DOCX_PATH,
    CHARACTERS_DIR,
)

# 👉 Updated to retry Saint Flamingo
RETRY = {
    "Saint Flamingo": "saint-flamingo",
}

print("Reading novel...")
novel_text = read_docx(DOCX_PATH)

for name, slug in RETRY.items():
    print(f"Retrying {name}...")
    for attempt in range(3):
        data = extract_character(name, slug, novel_text)
        if data:
            # Special handling if needed
            if slug == "hackermouth":
                data = hackermouth_override(data)

            out_path = CHARACTERS_DIR / f"{slug}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"  ✓ Saved {slug}.json")
            break

        print(f"  attempt {attempt+1} failed, retrying...")
        time.sleep(3)
    else:
        print(f"  ✗ {name} failed all 3 attempts")