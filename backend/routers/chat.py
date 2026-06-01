"""MultiVera chat router — conversation endpoint with all modes."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
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


# ── Streaming Chat (SSE) ──────────────────────────────────────────────────────

@router.post("/chat/stream")
def chat_stream(
    body: ChatBody,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream a chat response via Server-Sent Events (SSE)."""
    import json as _json

    # Validate project
    project = db.query(Project).filter(Project.id == body.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate characters
    characters = db.query(Character).filter(Character.id.in_(body.character_ids)).all()
    if not characters:
        raise HTTPException(status_code=404, detail="No valid characters found")

    # Validate mode
    valid_modes = {"story-locked", "post-end", "casual", "multi-character", "agent"}
    if body.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Use one of: {valid_modes}")

    try:
        client = get_ollama_client()
        model = OLLAMA_MODEL
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LLM backend unavailable: {exc}")

    request = ChatRequest(
        conversation_id=body.conversation_id,
        project_id=body.project_id,
        character_ids=body.character_ids,
        commit_id=body.commit_id,
        mode=body.mode,
        message=body.message,
    )

    # Import stream_chat_turn from engine_service
    from backend.services.engine_service import stream_chat_turn

    def event_generator():
        try:
            for chunk in stream_chat_turn(
                db=db,
                request=request,
                client=client,
                model=model,
            ):
                yield chunk
        except Exception as exc:
            logger.exception("Stream error")
            yield f"data: {_json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── OpenRouter Streaming Chat (SSE) ──────────────────────────────────────────

@router.post("/chat/openrouter/stream")
def chat_openrouter_stream(
    body: OpenRouterBody,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream a chat response via OpenRouter with SSE."""
    import json as _json
    import httpx

    # Validate
    project = db.query(Project).filter(Project.id == body.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    characters = db.query(Character).filter(Character.id.in_(body.character_ids)).all()
    if not characters:
        raise HTTPException(status_code=404, detail="No valid characters found")

    # Build system prompt
    from backend.services.engine_service import build_system_prompt, create_conversation, build_chat_messages

    primary_character = characters[0]
    commit = None
    if body.commit_id:
        commit = db.query(Commit).filter(Commit.id == body.commit_id).first()

    if body.conversation_id:
        conv = db.query(Conversation).filter(Conversation.id == body.conversation_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conv = create_conversation(
            db=db,
            project_id=body.project_id,
            character_ids=body.character_ids,
            commit_id=body.commit_id,
            mode=body.mode,
        )

    history = conv.messages or []
    plain_history = [{"role": m["role"], "content": m["content"]} for m in history]

    messages = build_chat_messages(
        character=primary_character,
        commit=commit,
        history=plain_history,
        mode=body.mode,
    )
    messages.append({"role": "user", "content": body.message})

    # Convert for OpenRouter
    or_messages = []
    for m in messages:
        role = m["role"]
        if role == "system":
            role = "user"
        or_messages.append({"role": role, "content": m["content"]})

    def event_generator():
        # Emit meta event first
        yield f"data: {_json.dumps({'type': 'meta', 'conversation_id': conv.id, 'character_id': primary_character.id, 'character_name': primary_character.name, 'mode': body.mode})}\n\n"

        full_text = ""
        try:
            with httpx.Client(timeout=120) as http_client:
                resp = http_client.stream(
                    "POST",
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {body.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": body.model,
                        "messages": or_messages,
                        "stream": True,
                    },
                )
                with resp as response:
                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = _json.loads(data)
                                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    full_text += delta
                                    yield f"data: {_json.dumps({'type': 'token', 'content': delta})}\n\n"
                            except _json.JSONDecodeError:
                                continue
        except Exception as exc:
            logger.exception("OpenRouter stream error")
            yield f"data: {_json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
            return

        # Store messages
        user_msg = {"role": "user", "content": body.message}
        assistant_msg = {
            "role": "assistant",
            "content": full_text,
            "character_id": primary_character.id,
            "character_name": primary_character.name,
        }
        updated = list(history) + [user_msg, assistant_msg]
        conv.messages = updated
        db.commit()

        yield f"data: {_json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── OpenRouter Streaming Chat (SSE) ──────────────────────────────────────────

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


# ── OpenRouter Chat ───────────────────────────────────────────────────────────

class OpenRouterBody(BaseModel):
    conversation_id: str | None = None
    project_id: int
    character_ids: List[int]
    commit_id: int | None = None
    mode: str = "story-locked"
    message: str
    model: str = "meta-llama/llama-3.1-8b-instruct:free"
    api_key: str


@router.post("/chat/openrouter", response_model=ChatResponse)
def chat_openrouter(
    body: OpenRouterBody,
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Chat via OpenRouter API (supports Claude, GPT, Llama, etc.)."""
    import httpx

    # Validate project
    project = db.query(Project).filter(Project.id == body.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate characters
    characters = db.query(Character).filter(Character.id.in_(body.character_ids)).all()
    if not characters:
        raise HTTPException(status_code=404, detail="No valid characters found")

    # Build system prompt using the same engine as Ollama path
    from backend.services.engine_service import build_system_prompt, create_conversation, build_chat_messages

    primary_character = characters[0]
    commit = None
    if body.commit_id:
        commit = db.query(Commit).filter(Commit.id == body.commit_id).first()

    # Load or create conversation
    if body.conversation_id:
        conv = db.query(Conversation).filter(Conversation.id == body.conversation_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conv = create_conversation(
            db=db,
            project_id=body.project_id,
            character_ids=body.character_ids,
            commit_id=body.commit_id,
            mode=body.mode,
        )

    # Build messages
    history = conv.messages or []
    plain_history = [{"role": m["role"], "content": m["content"]} for m in history]

    messages = build_chat_messages(
        character=primary_character,
        commit=commit,
        history=plain_history,
        mode=body.mode,
    )
    messages.append({"role": "user", "content": body.message})

    # Call OpenRouter
    or_messages = []
    for m in messages:
        role = m["role"]
        if role == "system":
            role = "user"  # OpenRouter handles system via first user msg
        or_messages.append({"role": role, "content": m["content"]})

    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {body.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": body.model,
                    "messages": or_messages,
                },
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"OpenRouter error: {resp.text}")
        data = resp.json()
        assistant_text = data["choices"][0]["message"]["content"].strip()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenRouter request timed out")
    except Exception as exc:
        logger.exception("OpenRouter chat failed")
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {exc}")

    # Store messages
    user_msg = {"role": "user", "content": body.message}
    assistant_msg = {
        "role": "assistant",
        "content": assistant_text,
        "character_id": primary_character.id,
        "character_name": primary_character.name,
    }
    updated = list(history) + [user_msg, assistant_msg]
    conv.messages = updated
    db.commit()

    return ChatResponse(
        conversation_id=conv.id,
        message=ConversationMessage(
            role="assistant",
            content=assistant_text,
            character_id=primary_character.id,
            character_name=primary_character.name,
        ),
        mode=body.mode,
        knowledge_gate_active=body.mode in {"story-locked", "post-end", "multi-character"},
    )

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


# ── Ollama Proxy (avoids CORS issues from browser) ───────────────────────────

class OllamaProxyBody(BaseModel):
    host: str = "http://100.110.224.126:11434"


@router.post("/ollama/models")
def ollama_models_proxy(body: OllamaProxyBody) -> APIResponse:
    """Proxy to list Ollama models (avoids browser CORS)."""
    import httpx
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{body.host}/api/tags")
        if resp.status_code != 200:
            return APIResponse(success=False, message=f"Ollama returned {resp.status_code}", data={})
        data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        return APIResponse(success=True, message=f"Found {len(models)} models", data={"models": models})
    except Exception as exc:
        return APIResponse(success=False, message=str(exc), data={})


@router.post("/ollama/test")
def ollama_test_proxy(body: OllamaProxyBody) -> APIResponse:
    """Proxy to test Ollama connection (avoids browser CORS)."""
    import httpx
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{body.host}/api/tags")
        if resp.status_code == 200:
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            return APIResponse(success=True, message=f"Connected — {len(models)} models available", data={"models": models})
        return APIResponse(success=False, message=f"Ollama returned {resp.status_code}", data={})
    except Exception as exc:
        return APIResponse(success=False, message=str(exc), data={})
