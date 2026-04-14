#!/usr/bin/env python3
"""Retry failed characters from vera_extract.py"""
import json, re, time, sys
from pathlib import Path
from vera_extract import (
    read_docx, ollama_generate, extract_character,
    hackermouth_override, DOCX_PATH, CHARACTERS_DIR, CHARACTER_SLUGS
)

RETRY = {
    "Nalis Kurogisto": "nalis-kurogisto",
    "Ma Boyas": "ma-boyas",
}

print("Reading novel...")
novel_text = read_docx(DOCX_PATH)

for name, slug in RETRY.items():
    print(f"Retrying {name}...")
    for attempt in range(3):
        data = extract_character(name, slug, novel_text)
        if data:
            out_path = CHARACTERS_DIR / f"{slug}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"  ✓ Saved {slug}.json")
            break
        print(f"  attempt {attempt+1} failed, retrying...")
        time.sleep(3)
    else:
        print(f"  ✗ {name} failed all 3 attempts")

