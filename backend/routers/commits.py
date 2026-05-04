"""MultiVera commits router — timeline checkpoint CRUD."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Character, Commit, Project
from backend.schemas import APIResponse, CommitCreate, CommitOut, CommitUpdate
from backend.services.timeline_service import (
    build_timeline_for_character,
    build_timeline_for_project,
    get_character_timeline,
    reorder_commits,
)

router = APIRouter(tags=["commits"])


def _serialize_commit(commit: Commit) -> Dict[str, Any]:
    return {
        "id": commit.id,
        "project_id": commit.project_id,
        "character_id": commit.character_id,
        "commit_id": commit.commit_id,
        "title": commit.title,
        "location": commit.location,
        "situation": commit.situation,
        "knows": commit.knows or [],
        "does_not_know": commit.does_not_know or [],
        "chapter": commit.chapter,
        "scene": commit.scene,
        "order_index": commit.order_index,
        "is_start": commit.is_start,
        "is_end": commit.is_end,
        "extra": commit.extra or {},
        "created_at": commit.created_at,
        "updated_at": commit.updated_at,
    }


# ── Character timeline ──────────────────────────────────────────────────────

@router.get("/characters/{character_id}/commits", response_model=List[CommitOut])
def list_commits_for_character(
    character_id: int,
    db: Session = Depends(get_db),
) -> List[CommitOut]:
    """Get all timeline checkpoints for a character."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    commits = get_character_timeline(db, character_id)
    return [CommitOut.model_validate(_serialize_commit(c)) for c in commits]


@router.post("/characters/{character_id}/commits", response_model=CommitOut, status_code=status.HTTP_201_CREATED)
def create_commit(
    character_id: int,
    body: CommitCreate,
    db: Session = Depends(get_db),
) -> CommitOut:
    """Create a commit for a character."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    commit = Commit(
        project_id=character.project_id,
        character_id=character_id,
        commit_id=body.commit_id,
        title=body.title,
        location=body.location,
        situation=body.situation,
        knows=body.knows or [],
        does_not_know=body.does_not_know or [],
        chapter=body.chapter,
        scene=body.scene,
        order_index=body.order_index,
        is_start=body.is_start,
        is_end=body.is_end,
        extra=body.extra or {},
    )
    db.add(commit)
    db.commit()
    db.refresh(commit)
    return CommitOut.model_validate(_serialize_commit(commit))


# ── Single commit operations ────────────────────────────────────────────────

@router.get("/commits/{commit_id}", response_model=CommitOut)
def get_commit(commit_id: int, db: Session = Depends(get_db)) -> CommitOut:
    """Get a single commit."""
    commit = db.query(Commit).filter(Commit.id == commit_id).first()
    if not commit:
        raise HTTPException(status_code=404, detail="Commit not found")
    return CommitOut.model_validate(_serialize_commit(commit))


@router.put("/commits/{commit_id}", response_model=CommitOut)
def update_commit(
    commit_id: int,
    body: CommitUpdate,
    db: Session = Depends(get_db),
) -> CommitOut:
    """Update a commit."""
    commit = db.query(Commit).filter(Commit.id == commit_id).first()
    if not commit:
        raise HTTPException(status_code=404, detail="Commit not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(commit, key):
            setattr(commit, key, value)

    db.commit()
    db.refresh(commit)
    return CommitOut.model_validate(_serialize_commit(commit))


@router.delete("/commits/{commit_id}")
def delete_commit(commit_id: int, db: Session = Depends(get_db)) -> APIResponse:
    """Delete a commit."""
    commit = db.query(Commit).filter(Commit.id == commit_id).first()
    if not commit:
        raise HTTPException(status_code=404, detail="Commit not found")
    db.delete(commit)
    db.commit()
    return APIResponse(success=True, message=f"Commit {commit_id} deleted")


# ── Auto-build timeline ─────────────────────────────────────────────────────

class TimelineBuildBody(BaseModel):
    character_id: int
    auto_generate: bool = True
    commit_count: int = 3


@router.post("/projects/{project_id}/timeline/build")
def build_project_timeline(
    project_id: int,
    body: TimelineBuildBody,
    db: Session = Depends(get_db),
) -> APIResponse:
    """Auto-build timeline for a project or specific character."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    summary = build_timeline_for_project(
        db,
        project_id=project_id,
        auto_generate=body.auto_generate,
        commit_count=body.commit_count,
    )
    return APIResponse(success=True, data=summary)
