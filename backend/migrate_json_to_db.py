"""MultiVera JSON-to-SQLite migration script.

Reads all existing JSON files from:
  characters/, commits/, locations/, factions/, weapons/

Inserts them into SQLite via SQLAlchemy ORM.
Creates a default Project called "Final Fantasy Tactics" that owns all existing data.
Preserves all relationships.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.config import (
    BASE_DIR,
    CHARACTERS_DIR,
    COMMITS_DIR,
    FACTIONS_DIR,
    LOCATIONS_DIR,
    WEAPONS_DIR,
    DEFAULT_PROJECT_NAME,
)
from backend.database import SessionLocal, engine, Base
from backend.models import (
    Base,
    Character,
    Commit,
    Faction,
    Location,
    Project,
    Weapon,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("multivera.migrate")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def create_tables() -> None:
    logger.info("Creating tables...")
    Base.metadata.create_all(bind=engine)


def create_default_project(db: Session) -> Project:
    existing = db.query(Project).filter(Project.name == DEFAULT_PROJECT_NAME).first()
    if existing:
        logger.info("Default project already exists: id=%s", existing.id)
        return existing

    project = Project(name=DEFAULT_PROJECT_NAME, description="Final Fantasy Tactics — War of the Lions")
    db.add(project)
    db.commit()
    db.refresh(project)
    logger.info("Created default project: id=%s", project.id)
    return project


def migrate_characters(db: Session, project: Project) -> Dict[str, int]:
    """Migrate character JSON files. Returns slug->id mapping."""
    mapping: Dict[str, int] = {}
    files = sorted(CHARACTERS_DIR.glob("*.json"))
    logger.info("Migrating %d characters...", len(files))

    for path in files:
        data = load_json(path)
        slug = data.get("slug", path.stem)
        speech = data.get("speech_patterns") or data.get("voice") or {}
        relationships = data.get("relationships") or {}
        knowledge = data.get("knowledge_gates") or {}

        character = Character(
            project_id=project.id,
            slug=slug,
            name=data.get("name", slug),
            role=data.get("role") or data.get("title"),
            affiliation=data.get("affiliation"),
            origin=data.get("origin"),
            appearance=data.get("appearance") or data.get("physical"),
            personality=data.get("personality") if isinstance(data.get("personality"), list) else [],
            tone=data.get("tone"),
            languages=data.get("languages", []),
            speech_patterns=speech,
            relationships=relationships,
            notable_quotes=data.get("notable_quotes", []),
            weapons_tools=data.get("weapons_tools") or data.get("items", []),
            backstory_summary=data.get("backstory_summary"),
            roleplay_instructions=data.get("roleplay_instructions"),
            knowledge_gates=knowledge,
            is_player=False,
            is_active=True,
        )
        db.add(character)
        db.flush()  # get id without committing
        mapping[slug] = character.id
        logger.info("  Character %s (id=%s)", slug, character.id)

    db.commit()
    return mapping


def migrate_commits(
    db: Session,
    project: Project,
    character_mapping: Dict[str, int],
) -> None:
    """Migrate commit JSON files, linking to characters by best-effort slug matching."""
    files = sorted(COMMITS_DIR.glob("*.json"))
    logger.info("Migrating %d commits...", len(files))

    for path in files:
        data = load_json(path)
        commit_id = data.get("commit_id", path.stem)

        # Best-effort character linkage: try to find a character whose slug
        # is a prefix of the commit filename or vice versa.
        linked_character_id: Optional[int] = None
        for slug, char_id in character_mapping.items():
            if slug.replace("-", "_") in path.stem or path.stem.startswith(slug.replace("-", "_")):
                linked_character_id = char_id
                break
            # Special cases
            if slug == "hackermouth" and "hackermouth" in path.stem:
                linked_character_id = char_id
                break
            if slug == "manus-flatfoot" and ("manus" in path.stem or "motif_of_manus" in path.stem):
                linked_character_id = char_id
                break
            if slug == "roz-kolora" and "roz" in path.stem:
                linked_character_id = char_id
                break
            if slug == "azula-sabra" and "azula" in path.stem:
                linked_character_id = char_id
                break
            if slug == "koden-bushi-bloodflower" and "kbloodflower" in path.stem:
                linked_character_id = char_id
                break
            if slug == "sesso-dolce" and "sd" in path.stem:
                linked_character_id = char_id
                break

        commit = Commit(
            project_id=project.id,
            character_id=linked_character_id,
            commit_id=commit_id,
            title=data.get("title"),
            location=data.get("location"),
            situation=data.get("situation"),
            knows=data.get("knows", []),
            does_not_know=data.get("does_not_know", []),
            chapter=data.get("chapter"),
            scene=data.get("scene"),
            order_index=0,
            is_start=False,
            is_end=False,
        )
        db.add(commit)
        logger.info(
            "  Commit %s (char_id=%s)",
            commit_id,
            linked_character_id,
        )

    db.commit()


def migrate_locations(db: Session, project: Project) -> None:
    files = sorted(LOCATIONS_DIR.glob("*.json"))
    logger.info("Migrating %d locations...", len(files))
    for path in files:
        data = load_json(path)
        loc = Location(
            project_id=project.id,
            name=data.get("name", path.stem),
            description=data.get("description"),
        )
        db.add(loc)
    db.commit()


def migrate_factions(db: Session, project: Project) -> None:
    files = sorted(FACTIONS_DIR.glob("*.json"))
    logger.info("Migrating %d factions...", len(files))
    for path in files:
        data = load_json(path)
        fac = Faction(
            project_id=project.id,
            name=data.get("name", path.stem),
            description=data.get("description"),
        )
        db.add(fac)
    db.commit()


def migrate_weapons(db: Session, project: Project) -> None:
    files = sorted(WEAPONS_DIR.glob("*.json"))
    logger.info("Migrating %d weapons...", len(files))
    for path in files:
        data = load_json(path)
        wpn = Weapon(
            project_id=project.id,
            name=data.get("name", path.stem),
            description=data.get("description"),
        )
        db.add(wpn)
    db.commit()


def main() -> None:
    create_tables()
    db = SessionLocal()
    try:
        project = create_default_project(db)
        char_map = migrate_characters(db, project)
        migrate_commits(db, project, char_map)
        migrate_locations(db, project)
        migrate_factions(db, project)
        migrate_weapons(db, project)

        # Update sources list
        sources: List[str] = []
        sources.extend([p.name for p in CHARACTERS_DIR.glob("*.json")])
        sources.extend([p.name for p in COMMITS_DIR.glob("*.json")])
        project.sources = sources
        db.commit()

        logger.info("Migration complete.")
        logger.info("  Project: %s (id=%s)", project.name, project.id)
        logger.info("  Characters: %s", len(char_map))
        logger.info("  Commits: %s", db.query(Commit).filter(Commit.project_id == project.id).count())
        logger.info("  Locations: %s", db.query(Location).filter(Location.project_id == project.id).count())
        logger.info("  Factions: %s", db.query(Faction).filter(Faction.project_id == project.id).count())
        logger.info("  Weapons: %s", db.query(Weapon).filter(Weapon.project_id == project.id).count())
    finally:
        db.close()


if __name__ == "__main__":
    main()
