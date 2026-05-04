"""MultiVera projects router — CRUD for projects/worlds."""
from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Character, Commit, Conversation, Faction, Location, LoreChunk, Project, Weapon
from backend.schemas import APIResponse, ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_counts(db: Session, project: Project) -> dict[str, int]:
    return {
        "character_count": db.query(Character).filter(Character.project_id == project.id).count(),
        "commit_count": db.query(Commit).filter(Commit.project_id == project.id).count(),
    }


@router.get("", response_model=List[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> List[ProjectOut]:
    """List all projects with character and commit counts."""
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    result: List[ProjectOut] = []
    for p in projects:
        counts = _project_counts(db, p)
        result.append(
            ProjectOut(
                id=p.id,
                name=p.name,
                description=p.description,
                sources=p.sources or [],
                created_at=p.created_at,
                updated_at=p.updated_at,
                character_count=counts["character_count"],
                commit_count=counts["commit_count"],
            )
        )
    return result


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)) -> ProjectOut:
    """Create a new project/world."""
    project = Project(name=body.name, description=body.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        sources=project.sources or [],
        created_at=project.created_at,
        updated_at=project.updated_at,
        character_count=0,
        commit_count=0,
    )


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectOut:
    """Get a single project with counts."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    counts = _project_counts(db, project)
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        sources=project.sources or [],
        created_at=project.created_at,
        updated_at=project.updated_at,
        character_count=counts["character_count"],
        commit_count=counts["commit_count"],
    )


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)) -> APIResponse:
    """Delete a project and all its associated data."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return APIResponse(success=True, message=f"Project {project_id} deleted")
