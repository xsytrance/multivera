"""MultiVera ingestion router — file upload + text processing pipeline."""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import MAX_UPLOAD_SIZE_MB, SUPPORTED_UPLOAD_EXTENSIONS
from backend.database import get_db
from backend.models import Character, Commit, LoreChunk, Project
from backend.schemas import APIResponse, IngestStatus
from backend.services.extraction_service import extract_character_from_text
from backend.services.rag_service import ingest_file, search_lore

router = APIRouter(tags=["ingestion"])

logger = logging.getLogger("multivera.ingestion_router")


@router.post("/projects/{project_id}/upload")
async def upload_file(
    project_id: int,
    file: UploadFile = File(...),
    extract_characters: bool = Form(False),
    db: Session = Depends(get_db),
) -> APIResponse:
    """Upload a file (.txt, .md, .pdf, .docx) for a project.

    Optional: trigger character extraction from the uploaded text.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {suffix}. Supported: {SUPPORTED_UPLOAD_EXTENSIONS}",
        )

    # Save to temp
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {size_mb:.1f}MB (max {MAX_UPLOAD_SIZE_MB}MB)",
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="wb") as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    try:
        # Ingest into Chroma
        result = ingest_file(
            path=tmp_path,
            project_id=project_id,
        )

        extracted: List[Dict[str, Any]] = []
        if extract_characters:
            # Read text for extraction
            from backend.services.rag_service import extract_text_from_file
            try:
                text = extract_text_from_file(tmp_path)
                char = extract_character_from_text(
                    db=db,
                    project_id=project_id,
                    name=Path(file.filename).stem.replace("_", " ").replace("-", " ").title(),
                    slug=Path(file.filename).stem,
                    text=text,
                )
                if char:
                    extracted.append({"id": char.id, "name": char.name, "slug": char.slug})
            except Exception as exc:
                logger.warning("Character extraction failed for %s: %s", file.filename, exc)

        # Track source in project
        sources = set(project.sources or [])
        sources.add(file.filename)
        project.sources = list(sources)
        db.commit()

        return APIResponse(
            success=True,
            message=f"Uploaded {file.filename}: {result['chunks_stored']} chunks stored",
            data={
                "file": file.filename,
                "chunks_stored": result["chunks_stored"],
                "collection_name": result["collection_name"],
                "extracted_characters": extracted,
            },
        )
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/projects/{project_id}/ingest")
def trigger_ingestion(
    project_id: int,
    db: Session = Depends(get_db),
) -> APIResponse:
    """Trigger ingestion for all supported files in the project's knowledge directory."""
    from backend.config import KNOWLEDGE_DIR
    from backend.services.rag_service import ingest_directory

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_knowledge_dir = KNOWLEDGE_DIR / str(project_id)
    if not project_knowledge_dir.exists():
        return APIResponse(
            success=True,
            message="No knowledge directory found; nothing to ingest",
            data={"directory": str(project_knowledge_dir)},
        )

    result = ingest_directory(
        directory=project_knowledge_dir,
        project_id=project_id,
    )

    return APIResponse(
        success=True,
        message=f"Ingested {result['files_processed']}/{result['files_found']} files",
        data=result,
    )


class LoreSearchBody(BaseModel):
    query: str
    n_results: int = 3
    character_id: Optional[int] = None
    commit_id: Optional[int] = None


@router.post("/projects/{project_id}/lore/search")
def search_project_lore(
    project_id: int,
    body: LoreSearchBody,
    db: Session = Depends(get_db),
) -> APIResponse:
    """Search lore chunks within a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    matches = search_lore(
        query=body.query,
        project_id=project_id,
        n_results=body.n_results,
        character_id=body.character_id,
        commit_id=body.commit_id,
    )
    return APIResponse(success=True, data={"matches": matches, "count": len(matches)})
