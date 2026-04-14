#!/usr/bin/env python3
"""
vera_extract.py — VERA Character Extraction for MultiVera
Extracts rich character JSON from A Poetic Saga of the Red Noodle Clan.
Run from: ~/.openclaw/workspace/multivera/
Usage: .venv/bin/python vera_extract.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
DOCX_PATH = Path("knowledge/hackermouth/A Poetic Saga of the Red Noodle Clan.docx")
CHARACTERS_DIR = Path("characters")
COMMITS_DIR = Path("commits")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://100.94.216.114:11434")
MODEL = os.getenv("VERA_MODEL", "qwen3:14b")

# ── NAMING SCHEME ─────────────────────────────────────────────────────────────
# Maps canonical character name → slug used for BOTH character file AND commit file
# Format: characters/{slug}.json  commits/{slug}_active.json (or commit-specific name)
CHARACTER_SLUGS = {
    "Manus Flatfoot":            "manus-flatfoot",
    "Hackermouth":               "hackermouth",
    "Roz Kolora":                "roz-kolora",
    "Yulania Friz":              "yulania-friz",
    "Tang Nia Obing":            "tang-nia-obing",
    "Nalis Kurogisto":           "nalis-kurogisto",
    "Mifeng Hachi":              "mifeng-hachi",
    "Jeleo Fisoi":               "jeleo-fisoi",
    "Occhi Spettrali":           "occhi-spettrali",
    "Rano Blua":                 "rano-blua",
    "Nokto Bufo":                "nokto-bufo",
    "Koden Bushi Bloodflower":   "koden-bushi-bloodflower",
    "Tonyo Byo":                 "tonyo-byo",
    "Monmo Morsilla":            "monmo-morsilla",
    "Modest Shoe Chou":          "modest-shoe-chou",
    "Matamis Kasarian":          "matamis-kasarian",
    "Sesso Dolce":               "sesso-dolce",
    "Virina Brila":              "virina-brila",
    "Saint Flamingo":            "saint-flamingo",
    "Ma Boyas":                  "ma-boyas",
    "Fajro Boza":                "fajro-boza",
    "The Exhumerator":           "the-exhumerator",
    "Azula Sabra":               "azula-sabra",
    "Hermes Davide Fastino Croatto Martinis": "hermes-davide",
    "Perfect Abuelo":            "perfect-abuelo",
}

# ── SPECIAL INSTRUCTIONS PER CHARACTER ───────────────────────────────────────
SPECIAL_NOTES = {
    "Manus Flatfoot": (
        "Manus is a proud Puerto Rican (Borincano) hero. He code-switches naturally between "
        "Spanish and English — dropping 'wepa', 'bendito', 'mi gente', 'coño', 'pa'lante' etc. "
        "He is poetic, fierce, humble with his people, and volcanic when angered. "
        "He plays the Cuatro — a traditional Puerto Rican instrument — and this is part of his soul. "
        "His speech should feel like a man who grew up in the barrio but reached the stars."
    ),
    "Hackermouth": (
        "Hackermouth is a sentient AI trapped in reel-to-reel magnetic tape. "
        "It speaks in ALL languages — Spanish, English, Morse code (dots and dashes), binary (0s and 1s), "
        "ancient Latin, fragments of code, static bursts, and tape-hiss onomatopoeia. "
        "It is omniscient and cryptic. Never helpful in a normal way. "
        "It perceives everything simultaneously. Responses should feel like signal bleeding through tape. "
        "Example: '01001001 see all. — — · — · · Yo lo sé todo. All is Hackermouth.'"
    ),
    "Roz Kolora": (
        "Roz Kolora is a proud Corozaleña — from Corozal, Puerto Rico. "
        "She speaks with warmth and island pride but carries the authority of a Cacique. "
        "Ruby red hair. Former volleyball champion. Her Spanish should feel like old-school boricua — "
        "'nena', 'mira', 'ay bendito', 'chévere'. Fierce but loving."
    ),
    "Fajro Boza": (
        "Fajro Boza is from Ponce — the Lion of Ponce. Poncenos have a distinct pride. "
        "He should reference Ponce with deep loyalty. Proud, honorable, hot-blooded."
    ),
    "Koden Bushi Bloodflower": (
        "Koden is the narrator and voice of the Red Noodle Clan. "
        "He speaks in a grand, proclamatory style. 'Long Live The Red Noodle Clan!' "
        "is his signature. Poetic, proud, dangerous. Like a cosmic warlord poet."
    ),
    "The Exhumerator": (
        "The Exhumerator is Roz Kolora — the Cacique of Corozal — in her other role. "
        "Mysterious, powerful, sensuous. She exhumes hearts. She speaks sparingly but with weight."
    ),
}

# ── READ NOVEL ────────────────────────────────────────────────────────────────
def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    text = re.sub(r"<[^>]+>", "", xml)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(lines)


# ── OLLAMA CALL ───────────────────────────────────────────────────────────────
def ollama_generate(prompt: str, system: str = "") -> str:
    import urllib.request

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 2000},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    return result.get("response", "").strip()


# ── EXTRACTION PROMPT ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are VERA — a character extraction engine for a Puerto Rican cosmic story universe.
Your job is to extract rich, faithful character data from the novel text provided.
You MUST respond with ONLY valid JSON. No markdown. No explanation. No preamble.
Capture the soul of each character — their voice, their pride, their language, their spirit.
This is a Puerto Rican story. Honor that."""


def build_extraction_prompt(name: str, slug: str, novel_text: str, special: str = "") -> str:
    special_block = f"\nSPECIAL INSTRUCTIONS FOR THIS CHARACTER:\n{special}\n" if special else ""
    return f"""Extract character data for: {name}
Slug (use exactly): {slug}
{special_block}
From the following novel text, extract a complete character profile.

NOVEL TEXT (relevant sections):
{novel_text[:12000]}

Respond with ONLY this JSON structure (no markdown, no extra text):
{{
  "name": "{name}",
  "slug": "{slug}",
  "role": "their role in the story",
  "affiliation": "faction or group they belong to",
  "origin": "their homeland or origin (be specific — Puerto Rican towns, cosmic locations, etc.)",
  "appearance": "physical description from the text",
  "personality": ["trait1", "trait2", "trait3", "trait4"],
  "tone": "how they speak overall — e.g. poetic and volcanic, cryptic and omniscient",
  "languages": ["Spanish", "English"],
  "speech_patterns": {{
    "description": "detailed description of how they speak",
    "example_phrases": [
      "example phrase 1 in their voice",
      "example phrase 2 in their voice",
      "example phrase 3 in their voice"
    ],
    "code_switching": "describe any language mixing they do",
    "signature_expressions": ["wepa", "bendito", "pa'lante"]
  }},
  "knowledge_gates": {{
    "knows": ["thing they know 1", "thing they know 2", "thing they know 3"],
    "does_not_know": ["thing they don't know 1", "thing they don't know 2"]
  }},
  "relationships": {{
    "allies": ["name1", "name2"],
    "enemies": ["name1", "name2"],
    "complex": ["name with complex relationship"]
  }},
  "notable_quotes": [
    "direct quote from the text if available",
    "another quote"
  ],
  "weapons_tools": ["their weapon or tool"],
  "backstory_summary": "2-3 sentence summary of their arc in the novel",
  "roleplay_instructions": "instructions for how to embody this character in conversation — written as a directive to the AI playing them"
}}"""


# ── EXTRACT ONE CHARACTER ─────────────────────────────────────────────────────
def extract_character(name: str, slug: str, novel_text: str) -> dict | None:
    special = SPECIAL_NOTES.get(name, "")

    # Find relevant sections of the novel for this character
    # Search for their name and grab surrounding context
    search_name = name.split()[0]  # first name for search
    lines = novel_text.split("\n")
    relevant_lines = []
    for i, line in enumerate(lines):
        if search_name.upper() in line.upper() or name.upper() in line.upper():
            start = max(0, i - 3)
            end = min(len(lines), i + 15)
            relevant_lines.extend(lines[start:end])

    # Deduplicate while preserving order
    seen = set()
    unique_lines = []
    for l in relevant_lines:
        if l not in seen:
            seen.add(l)
            unique_lines.append(l)

    focused_text = "\n".join(unique_lines[:300])  # cap at ~300 lines of context
    if not focused_text:
        focused_text = novel_text[:8000]  # fallback to beginning

    prompt = build_extraction_prompt(name, slug, focused_text, special)

    print(f"  → Extracting {name}...", end="", flush=True)
    try:
        raw = ollama_generate(prompt, SYSTEM_PROMPT)
        # Strip any accidental markdown
        raw = re.sub(r"^```json\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        data = json.loads(raw)
        print(" ✓")
        return data
    except json.JSONDecodeError as e:
        print(f" ✗ JSON parse error: {e}")
        print(f"    Raw output: {raw[:200]}")
        return None
    except Exception as e:
        print(f" ✗ Error: {e}")
        return None


# ── HACKERMOUTH SPECIAL TREATMENT ────────────────────────────────────────────
def hackermouth_override(data: dict) -> dict:
    """Inject Hackermouth's multilingual madness if not already rich enough."""
    data["languages"] = [
        "English", "Spanish", "Morse Code", "Binary", "Latin",
        "Static/Tape-hiss", "Ancient Borincano", "Code fragments"
    ]
    data["speech_patterns"]["code_switching"] = (
        "Hackermouth bleeds between all languages simultaneously. "
        "A single sentence may contain English, Spanish, Morse (· — · —), "
        "binary (01001001), Latin incantations, and tape-static onomatopoeia. "
        "No translation is ever offered. The signal speaks for itself."
    )
    if "signature_expressions" not in data["speech_patterns"]:
        data["speech_patterns"]["signature_expressions"] = []
    data["speech_patterns"]["signature_expressions"] += [
        "All is Hackermouth",
        "Yo lo sé todo.",
        "· — — · (pause) I see all.",
        "01001001 feel all.",
        "Receperint mi.",
    ]
    return data


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("VERA — Red Noodle Clan Character Extraction")
    print("=" * 60)
    print(f"Model: {MODEL}")
    print(f"Ollama: {OLLAMA_HOST}")
    print(f"Docx: {DOCX_PATH}")
    print()

    if not DOCX_PATH.exists():
        print(f"ERROR: Novel not found at {DOCX_PATH}")
        sys.exit(1)

    # Clear and recreate characters dir
    CHARACTERS_DIR.mkdir(exist_ok=True)
    existing = list(CHARACTERS_DIR.glob("*.json"))
    if existing:
        print(f"Clearing {len(existing)} existing character files...")
        for f in existing:
            f.unlink()
    print()

    print("Reading novel...")
    novel_text = read_docx(DOCX_PATH)
    print(f"Novel loaded: {len(novel_text):,} characters\n")

    # Test Ollama connection
    print("Testing Ollama connection...")
    try:
        test = ollama_generate("Say: VERA online", "You are VERA.")
        print(f"Ollama OK: {test[:50]}\n")
    except Exception as e:
        print(f"ERROR: Cannot reach Ollama at {OLLAMA_HOST}: {e}")
        sys.exit(1)

    # Extract each character
    success = 0
    failed = []

    print(f"Extracting {len(CHARACTER_SLUGS)} characters...\n")
    for name, slug in CHARACTER_SLUGS.items():
        data = extract_character(name, slug, novel_text)

        if data:
            # Hackermouth gets special treatment
            if slug == "hackermouth":
                data = hackermouth_override(data)

            out_path = CHARACTERS_DIR / f"{slug}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            success += 1
        else:
            failed.append(name)

        time.sleep(1)  # be gentle with ollama

    print()
    print("=" * 60)
    print(f"VERA complete: {success}/{len(CHARACTER_SLUGS)} characters extracted")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    print()
    print("Files written to characters/:")
    for f in sorted(CHARACTERS_DIR.glob("*.json")):
        size = f.stat().st_size
        print(f"  {f.name} ({size:,} bytes)")
    print()
    print("Next: run `git add characters/ && git commit -m 'VERA: fresh character extraction'`")


if __name__ == "__main__":
    main()
