"""MultiVera timeline building service.

Provides utilities for auto-building and managing character timelines (commits).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models import Character, Commit, Project
from backend.services.extraction_service import generate_commits_for_character

logger = logging.getLogger("multivera.timeline_service")


def get_character_timeline(db: Session, character_id: int) -> List[Commit]:
    """Get all commits for a character, ordered by order_index."""
    return (
        db.query(Commit)
        .filter(Commit.character_id == character_id)
        .order_by(Commit.order_index)
        .all()
    )


def build_timeline_for_character(
    db: Session,
    character_id: int,
    auto_generate: bool = False,
    commit_count: int = 3,
) -> List[Commit]:
    """Build or regenerate a character's timeline.

    If auto_generate is True and the character has no commits, use the LLM to generate them.
    """
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise ValueError(f"Character {character_id} not found")

    existing = get_character_timeline(db, character_id)
    if existing:
        logger.info("Character %s already has %d commits", character.name, len(existing))
        return existing

    if auto_generate:
        logger.info("Auto-generating timeline for %s", character.name)
        return generate_commits_for_character(db, character, count=commit_count)

    return []


def build_timeline_for_project(
    db: Session,
    project_id: int,
    auto_generate: bool = False,
    commit_count: int = 3,
) -> dict:
    """Build timelines for all characters in a project.

    Returns a summary dict with per-character results.
    """
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    summary = {
        "project_id": project_id,
        "characters_processed": 0,
        "commits_created": 0,
        "details": {},
    }

    for character in characters:
        commits = build_timeline_for_character(
            db, character.id, auto_generate=auto_generate, commit_count=commit_count
        )
        summary["characters_processed"] += 1
        summary["commits_created"] += len(commits)
        summary["details"][character.slug] = {
            "character_id": character.id,
            "commits_created": len(commits),
            "commit_ids": [c.commit_id for c in commits],
        }

    logger.info(
        "Project %s timeline build: %s characters, %s commits",
        project_id,
        summary["characters_processed"],
        summary["commits_created"],
    )
    return summary


def reorder_commits(db: Session, character_id: int, ordered_commit_ids: List[int]) -> List[Commit]:
    """Reorder commits for a character by reassigning order_index.

    ordered_commit_ids: list of Commit.id in desired order.
    """
    commits = (
        db.query(Commit)
        .filter(Commit.character_id == character_id)
        .all()
    )
    commit_map = {c.id: c for c in commits}

    for idx, commit_id in enumerate(ordered_commit_ids, start=1):
        if commit_id in commit_map:
            commit_map[commit_id].order_index = idx

    db.commit()
    return get_character_timeline(db, character_id)
