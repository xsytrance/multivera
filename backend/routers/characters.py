"""MultiVera characters router — CRUD + extraction endpoint."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Character, Commit, Project
from backend.schemas import (
    APIResponse,
    CharacterCreate,
    CharacterListOut,
    CharacterOut,
    CharacterUpdate,
)
from backend.services.extraction_service import extract_character_from_text

router = APIRouter(tags=["characters"])

logger = logging.getLogger("multivera.characters_router")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _serialize_character(character: Character) -> Dict[str, Any]:
    return {
        "id": character.id,
        "project_id": character.project_id,
        "slug": character.slug,
        "name": character.name,
        "role": character.role,
        "affiliation": character.affiliation,
        "origin": character.origin,
        "appearance": character.appearance,
        "personality": character.personality or [],
        "tone": character.tone,
        "languages": character.languages or [],
        "speech_patterns": character.speech_patterns or {},
        "relationships": character.relationships or {},
        "notable_quotes": character.notable_quotes or [],
        "weapons_tools": character.weapons_tools or [],
        "backstory_summary": character.backstory_summary,
        "roleplay_instructions": character.roleplay_instructions,
        "knowledge_gates": character.knowledge_gates or {},
        "is_player": character.is_player,
        "is_active": character.is_active,
        "extra": character.extra or {},
        "created_at": character.created_at,
        "updated_at": character.updated_at,
    }


# ── List / Create under project ──────────────────────────────────────────────

@router.get("/projects/{project_id}/characters", response_model=List[CharacterListOut])
def list_characters(
    project_id: int,
    db: Session = Depends(get_db),
) -> List[CharacterListOut]:
    """List all characters in a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    characters = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.name)
        .all()
    )
    return [
        CharacterListOut(
            id=c.id,
            project_id=c.project_id,
            slug=c.slug,
            name=c.name,
            role=c.role,
            is_active=c.is_active,
        )
        for c in characters
    ]


@router.post("/projects/{project_id}/characters", response_model=CharacterOut, status_code=status.HTTP_201_CREATED)
def create_character(
    project_id: int,
    body: CharacterCreate,
    db: Session = Depends(get_db),
) -> CharacterOut:
    """Create a character manually in a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Slug uniqueness check within project
    existing = (
        db.query(Character)
        .filter(Character.project_id == project_id, Character.slug == body.slug)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Slug already exists in this project")

    character = Character(
        project_id=project_id,
        slug=body.slug,
        name=body.name,
        role=body.role,
        affiliation=body.affiliation,
        origin=body.origin,
        appearance=body.appearance,
        personality=body.personality or [],
        tone=body.tone,
        languages=body.languages or [],
        speech_patterns=body.speech_patterns or {},
        relationships=body.relationships or {},
        notable_quotes=body.notable_quotes or [],
        weapons_tools=body.weapons_tools or [],
        backstory_summary=body.backstory_summary,
        roleplay_instructions=body.roleplay_instructions,
        knowledge_gates=body.knowledge_gates or {},
        is_player=body.is_player,
        is_active=body.is_active,
        extra=body.extra or {},
    )
    db.add(character)
    db.commit()
    db.refresh(character)
    return CharacterOut.model_validate(_serialize_character(character))


# ── Extract from text ───────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    name: str
    slug: str
    text: str
    special_instructions: str = ""
    model: str = "qwen3:14b"


@router.post("/projects/{project_id}/characters/extract", response_model=CharacterOut)
def extract_character(
    project_id: int,
    body: ExtractRequest,
    db: Session = Depends(get_db),
) -> CharacterOut:
    """Auto-extract a character from provided text using Ollama."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    character = extract_character_from_text(
        db=db,
        project_id=project_id,
        name=body.name,
        slug=body.slug,
        text=body.text,
        special_instructions=body.special_instructions,
        model=body.model,
    )
    if not character:
        raise HTTPException(status_code=500, detail="Character extraction failed")

    return CharacterOut.model_validate(_serialize_character(character))


# ── Single character operations ─────────────────────────────────────────────

@router.get("/characters/{character_id}", response_model=CharacterOut)
def get_character(character_id: int, db: Session = Depends(get_db)) -> CharacterOut:
    """Get a full character profile."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return CharacterOut.model_validate(_serialize_character(character))


@router.put("/characters/{character_id}", response_model=CharacterOut)
def update_character(
    character_id: int,
    body: CharacterUpdate,
    db: Session = Depends(get_db),
) -> CharacterOut:
    """Update a character (full editor support)."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(character, key):
            setattr(character, key, value)

    db.commit()
    db.refresh(character)
    return CharacterOut.model_validate(_serialize_character(character))


@router.delete("/characters/{character_id}")
def delete_character(character_id: int, db: Session = Depends(get_db)) -> APIResponse:
    """Delete a character."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    db.delete(character)
    db.commit()
    return APIResponse(success=True, message=f"Character {character_id} deleted")
