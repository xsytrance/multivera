"""MultiVera character extraction service.

Wraps vera_extract.py logic for API-driven character extraction from text.
Uses Ollama as the primary LLM backend (local-first).
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.config import OLLAMA_HOST
from backend.models import Character, Commit, Project

logger = logging.getLogger("multivera.extraction_service")

DEFAULT_MODEL = os.getenv("VERA_MODEL", "qwen3:14b")

EXTRACTION_SYSTEM_PROMPT = """You are VERA — a character extraction engine for a story universe.
Your job is to extract rich, faithful character data from the text provided.
You MUST respond with ONLY valid JSON. No markdown. No explanation. No preamble.
Capture the soul of each character — their voice, their language, their spirit."""


def _ollama_generate(
    prompt: str,
    system: str = "",
    model: str = DEFAULT_MODEL,
    host: str = OLLAMA_HOST,
) -> str:
    """Call Ollama /api/generate endpoint directly."""
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 2000},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    return result.get("response", "").strip()


def _clean_json_response(raw: str) -> str:
    """Strip accidental markdown fences from LLM JSON output."""
    raw = re.sub(r"^```json\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())
    return raw


def build_extraction_prompt(
    name: str,
    slug: str,
    text: str,
    special_instructions: str = "",
) -> str:
    """Build the VERA extraction prompt for a single character."""
    special_block = f"\nSPECIAL INSTRUCTIONS FOR THIS CHARACTER:\n{special_instructions}\n" if special_instructions else ""
    return f"""Extract character data for: {name}
Slug (use exactly): {slug}
{special_block}
From the following text, extract a complete character profile.

STORY TEXT:
{text[:12000]}

Respond with ONLY this JSON structure (no markdown, no extra text):
{{
  "name": "{name}",
  "slug": "{slug}",
  "role": "their role in the story",
  "affiliation": "faction or group they belong to",
  "origin": "their homeland or origin",
  "appearance": "physical description from the text",
  "personality": ["trait1", "trait2", "trait3", "trait4"],
  "tone": "how they speak overall",
  "languages": ["Spanish", "English"],
  "speech_patterns": {{
    "description": "detailed description of how they speak",
    "example_phrases": ["example phrase 1", "example phrase 2", "example phrase 3"],
    "code_switching": "describe any language mixing they do",
    "signature_expressions": ["expression1", "expression2"]
  }},
  "knowledge_gates": {{
    "knows": ["thing they know 1", "thing they know 2"],
    "does_not_know": ["thing they don't know 1"]
  }},
  "relationships": {{
    "allies": ["name1"],
    "enemies": ["name1"],
    "complex": ["name with complex relationship"]
  }},
  "notable_quotes": ["direct quote from the text"],
  "weapons_tools": ["their weapon or tool"],
  "backstory_summary": "2-3 sentence summary of their arc",
  "roleplay_instructions": "instructions for how to embody this character"
}}"""


def extract_character_from_text(
    db: Session,
    project_id: int,
    name: str,
    slug: str,
    text: str,
    special_instructions: str = "",
    model: str = DEFAULT_MODEL,
    host: str = OLLAMA_HOST,
) -> Optional[Character]:
    """Extract a single character from text and persist to the database."""
    logger.info("Extracting character '%s' (slug=%s) for project %s", name, slug, project_id)

    prompt = build_extraction_prompt(name, slug, text, special_instructions)
    try:
        raw = _ollama_generate(prompt, EXTRACTION_SYSTEM_PROMPT, model=model, host=host)
        raw = _clean_json_response(raw)
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("JSON decode error for %s: %s — raw: %s", name, exc, raw[:200])
        return None
    except Exception as exc:
        logger.error("Extraction failed for %s: %s", name, exc)
        return None

    # Map JSON to ORM
    speech = data.get("speech_patterns", {}) or {}
    relationships = data.get("relationships", {}) or {}
    knowledge = data.get("knowledge_gates", {}) or {}

    character = Character(
        project_id=project_id,
        slug=data.get("slug", slug),
        name=data.get("name", name),
        role=data.get("role"),
        affiliation=data.get("affiliation"),
        origin=data.get("origin"),
        appearance=data.get("appearance"),
        personality=data.get("personality", []),
        tone=data.get("tone"),
        languages=data.get("languages", []),
        speech_patterns=speech,
        relationships=relationships,
        notable_quotes=data.get("notable_quotes", []),
        weapons_tools=data.get("weapons_tools", []),
        backstory_summary=data.get("backstory_summary"),
        roleplay_instructions=data.get("roleplay_instructions"),
        knowledge_gates=knowledge,
        is_player=False,
        is_active=True,
    )

    db.add(character)
    db.commit()
    db.refresh(character)
    logger.info("Saved character %s (id=%s)", character.name, character.id)
    return character


def extract_characters_from_text(
    db: Session,
    project_id: int,
    text: str,
    character_hints: Optional[List[Dict[str, str]]] = None,
    model: str = DEFAULT_MODEL,
    host: str = OLLAMA_HOST,
) -> List[Character]:
    """Extract multiple characters from a body of text.

    character_hints: list of {"name": "...", "slug": "...", "special": "..."}
    If not provided, the LLM will be asked to discover characters automatically.
    """
    results: List[Character] = []

    if character_hints:
        for hint in character_hints:
            char = extract_character_from_text(
                db=db,
                project_id=project_id,
                name=hint["name"],
                slug=hint.get("slug", hint["name"].lower().replace(" ", "-")),
                text=text,
                special_instructions=hint.get("special", ""),
                model=model,
                host=host,
            )
            if char:
                results.append(char)
        return results

    # Auto-discover characters
    logger.info("Auto-discovering characters from text for project %s", project_id)
    auto_prompt = f"""You are a story analyst. Read the following story text and extract ALL named characters.
For each character, output ONLY a JSON array in this exact format:
[
  {{
    "name": "Character Name",
    "slug": "character-name",
    "role": "their role",
    "affiliation": "faction",
    "origin": "homeland",
    "appearance": "description",
    "personality": ["trait1", "trait2"],
    "tone": "how they speak",
    "languages": ["Spanish"],
    "speech_patterns": {{
      "description": "...",
      "example_phrases": ["..."],
      "code_switching": "...",
      "signature_expressions": ["..."]
    }},
    "knowledge_gates": {{"knows": ["..."], "does_not_know": ["..."]}},
    "relationships": {{"allies": [], "enemies": [], "complex": []}},
    "notable_quotes": [],
    "weapons_tools": [],
    "backstory_summary": "...",
    "roleplay_instructions": "..."
  }}
]

Story text:
{text[:15000]}
"""
    try:
        raw = _ollama_generate(auto_prompt, EXTRACTION_SYSTEM_PROMPT, model=model, host=host)
        raw = _clean_json_response(raw)
        characters_data = json.loads(raw)
    except Exception as exc:
        logger.error("Auto-discovery failed: %s", exc)
        return results

    if not isinstance(characters_data, list):
        logger.error("Auto-discovery returned non-list: %s", type(characters_data))
        return results

    for data in characters_data:
        if not isinstance(data, dict):
            continue
        char = extract_character_from_text(
            db=db,
            project_id=project_id,
            name=data.get("name", "Unknown"),
            slug=data.get("slug", "unknown"),
            text=text,
            special_instructions="",
            model=model,
            host=host,
        )
        if char:
            results.append(char)

    return results


def generate_commits_for_character(
    db: Session,
    character: Character,
    count: int = 3,
    model: str = DEFAULT_MODEL,
    host: str = OLLAMA_HOST,
) -> List[Commit]:
    """Generate timeline commits for a character using the LLM."""
    character_json = json.dumps({
        "name": character.name,
        "role": character.role,
        "backstory_summary": character.backstory_summary,
        "personality": character.personality,
    }, indent=2, ensure_ascii=False)

    prompt = f"""Based on this character's story arc, suggest {count} commit points representing major knowledge shifts.
For each generate a commit JSON in this format:
{{
  "commit_id": "unique_slug",
  "title": "Checkpoint Title",
  "location": "Where they are",
  "situation": "What is happening",
  "knows": ["fact 1", "fact 2"],
  "does_not_know": ["secret 1"],
  "chapter": "Chapter 1",
  "scene": "Scene 1",
  "order_index": 1,
  "is_start": false,
  "is_end": false
}}
Output ONLY valid JSON array of {count} commits.

Character JSON:
{character_json}
"""
    retry = prompt + "\nReturn raw JSON only. No markdown fences, no explanation."

    try:
        raw = _ollama_generate(prompt, retry, model=model, host=host)
        raw = _clean_json_response(raw)
        commits_data = json.loads(raw)
    except Exception as exc:
        logger.error("Commit generation failed for %s: %s", character.name, exc)
        return []

    if not isinstance(commits_data, list):
        logger.error("Commit generation returned non-list")
        return []

    saved: List[Commit] = []
    for idx, data in enumerate(commits_data):
        if not isinstance(data, dict):
            continue
        commit = Commit(
            project_id=character.project_id,
            character_id=character.id,
            commit_id=data.get("commit_id", f"commit_{idx}"),
            title=data.get("title"),
            location=data.get("location"),
            situation=data.get("situation"),
            knows=data.get("knows", []),
            does_not_know=data.get("does_not_know", []),
            chapter=data.get("chapter"),
            scene=data.get("scene"),
            order_index=data.get("order_index", idx),
            is_start=data.get("is_start", False),
            is_end=data.get("is_end", False),
        )
        db.add(commit)
        saved.append(commit)

    db.commit()
    for c in saved:
        db.refresh(c)
    logger.info("Generated %d commits for %s", len(saved), character.name)
    return saved
