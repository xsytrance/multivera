"""MultiVera export router — persona export, system prompt rendering."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Character, Commit
from backend.schemas import APIResponse, PersonaExport, SystemPromptOut
from backend.services.engine_service import build_system_prompt

router = APIRouter(tags=["export"])


def _character_to_dict(character: Character) -> Dict[str, Any]:
    return {
        "name": character.name,
        "slug": character.slug,
        "role": character.role,
        "affiliation": character.affiliation,
        "origin": character.origin,
        "appearance": character.appearance,
        "personality": character.personality,
        "tone": character.tone,
        "languages": character.languages,
        "speech_patterns": character.speech_patterns,
        "relationships": character.relationships,
        "notable_quotes": character.notable_quotes,
        "weapons_tools": character.weapons_tools,
        "backstory_summary": character.backstory_summary,
        "roleplay_instructions": character.roleplay_instructions,
        "knowledge_gates": character.knowledge_gates,
    }


def _commit_to_dict(commit: Commit) -> Dict[str, Any]:
    return {
        "commit_id": commit.commit_id,
        "title": commit.title,
        "location": commit.location,
        "situation": commit.situation,
        "knows": commit.knows,
        "does_not_know": commit.does_not_know,
        "chapter": commit.chapter,
        "scene": commit.scene,
        "order_index": commit.order_index,
        "is_start": commit.is_start,
        "is_end": commit.is_end,
    }


@router.get("/characters/{character_id}/system-prompt", response_model=SystemPromptOut)
def get_system_prompt(
    character_id: int,
    mode: str = Query("story-locked"),
    commit_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> SystemPromptOut:
    """Get the rendered system prompt for a character in a given mode.

    Query params:
    - mode: story-locked | post-end | casual | multi-character | agent
    - commit_id: optional commit for story-locked / multi-character modes
    """
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    commit = None
    if commit_id:
        commit = db.query(Commit).filter(Commit.id == commit_id).first()
        if not commit:
            raise HTTPException(status_code=404, detail="Commit not found")

    valid_modes = {"story-locked", "post-end", "casual", "multi-character", "agent"}
    if mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Use one of: {valid_modes}")

    prompt = build_system_prompt(
        character=character,
        commit=commit,
        mode=mode,
    )

    return SystemPromptOut(
        character_id=character.id,
        character_name=character.name,
        mode=mode,
        commit_id=commit_id,
        system_prompt=prompt,
    )


@router.post("/characters/{character_id}/export", response_model=PersonaExport)
def export_persona(
    character_id: int,
    mode: str = Query("story-locked"),
    commit_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> PersonaExport:
    """Export a persona JSON for external AI agent use.

    Query params:
    - mode: story-locked | post-end | casual | multi-character | agent
    - commit_id: optional commit
    """
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    commit = None
    if commit_id:
        commit = db.query(Commit).filter(Commit.id == commit_id).first()
        if not commit:
            raise HTTPException(status_code=404, detail="Commit not found")

    valid_modes = {"story-locked", "post-end", "casual", "multi-character", "agent"}
    if mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Use one of: {valid_modes}")

    system_prompt = build_system_prompt(
        character=character,
        commit=commit,
        mode=mode,
    )

    mode_rules = {
        "story-locked": "Character behaves as if inside the story at selected commit. Uses commit.knows and commit.does_not_know as hard boundaries.",
        "post-end": "Character reflects on full story with hindsight. Has access to ALL commits.",
        "casual": "Character adapted into assistant-style personality. Retains core identity but is helpful and conversational.",
        "multi-character": "Multiple characters interact in same conversation. Each maintains their own voice and knowledge.",
        "agent": "Exportable system prompt for external AI agents. Complete persona with mode rules.",
    }

    return PersonaExport(
        name=character.name,
        system_prompt=system_prompt,
        character_json=_character_to_dict(character),
        commit_json=_commit_to_dict(commit) if commit else None,
        mode_rules=mode_rules.get(mode, ""),
        version="multivera-v1",
    )
