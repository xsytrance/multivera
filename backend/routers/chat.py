"""MultiVera chat router — conversation endpoint with all modes."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import OLLAMA_MODEL
from backend.database import get_db
from backend.models import Character, Commit, Conversation, Project
from backend.schemas import (
    APIResponse,
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationMessage,
    ConversationOut,
)
from backend.services.engine_service import (
    chat_once_unified,
    get_ollama_client,
    list_available_models,
    run_chat_turn,
)

router = APIRouter(tags=["chat"])

logger = logging.getLogger("multivera.chat_router")


def _serialize_conversation(conv: Conversation) -> Dict[str, Any]:
    return {
        "id": conv.id,
        "project_id": conv.project_id,
        "character_ids": [c.id for c in conv.characters],
        "commit_id": conv.commit_id,
        "mode": conv.mode,
        "title": conv.title,
        "messages": [
            ConversationMessage(
                role=m.get("role", "user"),
                content=m.get("content", ""),
                character_id=m.get("character_id"),
                character_name=m.get("character_name"),
            )
            for m in (conv.messages or [])
        ],
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
    }


# ── Chat endpoint ─────────────────────────────────────────────────────────────

class ChatBody(BaseModel):
    conversation_id: str | None = None
    project_id: int
    character_ids: List[int]
    commit_id: int | None = None
    mode: str = "story-locked"
    message: str


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatBody,
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Start or continue a conversation.

    Modes: story-locked, post-end, casual, multi-character, agent
    """
    # Validate project
    project = db.query(Project).filter(Project.id == body.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate characters
    characters = db.query(Character).filter(Character.id.in_(body.character_ids)).all()
    if not characters:
        raise HTTPException(status_code=404, detail="No valid characters found")

    # Validate commit if provided
    if body.commit_id:
        commit = db.query(Commit).filter(Commit.id == body.commit_id).first()
        if not commit:
            raise HTTPException(status_code=404, detail="Commit not found")

    # Validate mode
    valid_modes = {"story-locked", "post-end", "casual", "multi-character", "agent"}
    if body.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Use one of: {valid_modes}")

    # Ollama client
    try:
        client = get_ollama_client()
        model = OLLAMA_MODEL
    except Exception as exc:
        logger.exception("Failed to create Ollama client")
        raise HTTPException(status_code=503, detail=f"LLM backend unavailable: {exc}")

    request = ChatRequest(
        conversation_id=body.conversation_id,
        project_id=body.project_id,
        character_ids=body.character_ids,
        commit_id=body.commit_id,
        mode=body.mode,
        message=body.message,
    )

    try:
        response = run_chat_turn(
            db=db,
            request=request,
            client=client,
            model=model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Chat turn failed")
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}")

    return response


# ── Conversation management ─────────────────────────────────────────────────

@router.get("/conversations", response_model=List[ConversationOut])
def list_conversations(db: Session = Depends(get_db)) -> List[ConversationOut]:
    """List all conversations."""
    conversations = db.query(Conversation).order_by(Conversation.updated_at.desc()).all()
    return [ConversationOut.model_validate(_serialize_conversation(c)) for c in conversations]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> ConversationOut:
    """Get a full conversation with messages."""
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationOut.model_validate(_serialize_conversation(conv))


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> APIResponse:
    """Delete a conversation."""
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(conv)
    db.commit()
    return APIResponse(success=True, message=f"Conversation {conversation_id} deleted")


# ── Health check for LLM backend ─────────────────────────────────────────────

@router.get("/chat/health")
def chat_health() -> APIResponse:
    """Check if the LLM backend is reachable."""
    try:
        models = list_available_models()
        return APIResponse(
            success=True,
            message="LLM backend reachable",
            data={"available_models": models, "default_model": OLLAMA_MODEL},
        )
    except Exception as exc:
        return APIResponse(
            success=False,
            message=f"LLM backend unreachable: {exc}",
            data={},
        )
