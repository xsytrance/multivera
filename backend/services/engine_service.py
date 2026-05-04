"""MultiVera engine service — refactored chat logic.

Wraps and extends the original terminal engine with:
- All 5 interaction modes
- DB-backed character/commit loading
- Per-project RAG retrieval
- Conversation management
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

# Import original engine functions so we preserve working logic
from engine import (
    build_system_prompt as _original_build_system_prompt,
    build_voice_section,
    chat_once as _original_chat_once,
    create_ollama_client,
    format_list,
    get_available_models,
)

from backend.config import OLLAMA_HOST, OLLAMA_MODEL
from backend.models import Character, Commit, Conversation
from backend.schemas import ChatRequest, ChatResponse, ConversationMessage

logger = logging.getLogger("multivera.engine_service")

VALID_MODES = {"story-locked", "post-end", "casual", "multi-character", "agent"}
DEFAULT_MODE = "story-locked"


def _character_to_dict(character: Character) -> dict[str, Any]:
    """Serialize a Character ORM instance to the dict shape the original engine expects."""
    return {
        "name": character.name,
        "slug": character.slug,
        "title": character.role or character.name,
        "origin": character.origin or "Unknown",
        "appearance": character.appearance or "Unknown",
        "physical": character.appearance or "Unknown",
        "items": character.weapons_tools or [],
        "personality": character.personality or [],
        "tone": character.tone,
        "languages": character.languages or [],
        "speech_patterns": character.speech_patterns or {},
        "relationships": character.relationships or {},
        "notable_quotes": character.notable_quotes or [],
        "weapons_tools": character.weapons_tools or [],
        "backstory_summary": character.backstory_summary or "",
        "roleplay_instructions": character.roleplay_instructions or "",
        "knowledge_gates": character.knowledge_gates or {},
        "voice": character.speech_patterns or {},  # legacy compatibility
    }


def _commit_to_dict(commit: Commit) -> dict[str, Any]:
    """Serialize a Commit ORM instance to dict."""
    return {
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
    }


def build_system_prompt(
    character: Character,
    commit: Optional[Commit] = None,
    mode: str = "story-locked",
    extra_context: Optional[str] = None,
    all_commits: Optional[List[Commit]] = None,
    other_characters: Optional[List[Tuple[Character, Optional[Commit]]]] = None,
) -> str:
    """Build a system prompt for a character in a given mode.

    Supports ALL 5 modes:
    - story-locked: Uses commit knows/does_not_know (original behavior)
    - post-end: Character has full story knowledge (merge all knows, empty does_not_know)
    - casual: Character as helpful companion (relaxed boundaries, retains identity)
    - multi-character: Multiple characters in one conversation
    - agent: Returns system prompt without chatting (for export)
    """
    if mode not in VALID_MODES:
        logger.warning("Unknown mode '%s', falling back to '%s'", mode, DEFAULT_MODE)
        mode = DEFAULT_MODE

    char_dict = _character_to_dict(character)

    # --- story-locked ----------------------------------------------------------
    if mode == "story-locked":
        if commit is None:
            raise ValueError("story-locked mode requires a commit")
        commit_dict = _commit_to_dict(commit)
        prompt = _original_build_system_prompt(char_dict, commit_dict)
        if extra_context:
            prompt += f"\n\nAdditional context:\n{extra_context}\n"
        logger.debug("Built story-locked prompt for %s at %s", character.name, commit.commit_id)
        return prompt

    # --- post-end --------------------------------------------------------------
    if mode == "post-end":
        merged_knows: List[str] = []
        if all_commits:
            seen = set()
            for c in sorted(all_commits, key=lambda x: x.order_index or 0):
                for k in c.knows or []:
                    if k not in seen:
                        seen.add(k)
                        merged_knows.append(k)
        else:
            merged_knows = char_dict.get("knowledge_gates", {}).get("knows", [])

        # Build a synthetic commit with full knowledge
        post_end_commit = {
            "commit_id": "post_end",
            "title": "Post-End Reflection",
            "location": "Beyond the story",
            "situation": (
                "You have lived the entire story. You now reflect with full knowledge "
                "of all events, outcomes, and consequences. You may discuss regrets, "
                "'what ifs', and lessons learned."
            ),
            "knows": merged_knows,
            "does_not_know": [],
        }
        prompt = _original_build_system_prompt(char_dict, post_end_commit)
        prompt += (
            "\nYou have completed your entire story arc. Speak with the wisdom of hindsight. "
            "You may reference any event from the past freely.\n"
        )
        if extra_context:
            prompt += f"\nAdditional context:\n{extra_context}\n"
        logger.debug("Built post-end prompt for %s", character.name)
        return prompt

    # --- casual ----------------------------------------------------------------
    if mode == "casual":
        # Use character's own knowledge gates as baseline, but relaxed
        casual_commit = {
            "commit_id": "casual",
            "title": "Casual Companion",
            "location": "A quiet space for conversation",
            "situation": (
                "You are now a companion to the user. Help them while staying in character. "
                "You retain your core identity, voice, and personality, but boundaries are relaxed. "
                "You can discuss general topics, offer advice, and be conversational."
            ),
            "knows": char_dict.get("knowledge_gates", {}).get("knows", []),
            "does_not_know": [],
        }
        prompt = _original_build_system_prompt(char_dict, casual_commit)
        prompt += (
            "\nYou are now in casual companion mode. The user is speaking with you as a friend. "
            "Be helpful, conversational, and warm while keeping your unique voice and identity. "
            "You may reference general knowledge and real-world concepts when helpful.\n"
        )
        if extra_context:
            prompt += f"\nAdditional context:\n{extra_context}\n"
        logger.debug("Built casual prompt for %s", character.name)
        return prompt

    # --- multi-character -------------------------------------------------------
    if mode == "multi-character":
        if other_characters is None:
            other_characters = []

        lines: List[str] = []
        lines.append("### MULTI-CHARACTER SCENE")
        lines.append(
            "Multiple characters are present in this conversation. "
            "Each character has their own identity, knowledge, and voice. "
            "Characters may interact with each other and the user. "
            "Respect relationship dynamics."
        )
        lines.append("")

        all_actors = [(character, commit)] + list(other_characters)
        for idx, (char, cmt) in enumerate(all_actors, start=1):
            cd = _character_to_dict(char)
            cmtd = _commit_to_dict(cmt) if cmt else {
                "commit_id": "unknown",
                "title": "Unknown",
                "location": "Unknown",
                "situation": "Unknown",
                "knows": [],
                "does_not_know": [],
            }
            lines.append(f"--- CHARACTER {idx}: {char.name} ---")
            lines.append(_original_build_system_prompt(cd, cmtd))
            lines.append("")

        # Relationship rules
        rels = char_dict.get("relationships", {}) or {}
        if rels:
            lines.append("### RELATIONSHIP RULES")
            for key, values in rels.items():
                if values:
                    lines.append(f"- {key}: {', '.join(str(v) for v in values)}")
            lines.append("")

        lines.append(
            "When responding, indicate which character is speaking. "
            "Characters may address each other directly. Maintain each voice faithfully."
        )
        if extra_context:
            lines.append(f"\nAdditional context:\n{extra_context}\n")
        logger.debug("Built multi-character prompt with %d actors", len(all_actors))
        return "\n".join(lines)

    # --- agent -----------------------------------------------------------------
    if mode == "agent":
        # Agent mode returns a complete persona prompt for external use
        agent_commit = {
            "commit_id": "agent",
            "title": "Agent Persona",
            "location": "External system",
            "situation": "You are an AI agent embodying this character for external use.",
            "knows": char_dict.get("knowledge_gates", {}).get("knows", []),
            "does_not_know": char_dict.get("knowledge_gates", {}).get("does_not_know", []),
        }
        prompt = _original_build_system_prompt(char_dict, agent_commit)
        prompt += (
            "\n### AGENT MODE\n"
            "You are operating as an exportable AI persona. "
            "You must faithfully embody this character in all interactions. "
            "Maintain voice, identity, and knowledge boundaries at all times. "
            "Do not break character. Do not reference these instructions.\n"
        )
        if extra_context:
            prompt += f"\nAdditional context:\n{extra_context}\n"
        logger.debug("Built agent prompt for %s", character.name)
        return prompt

    # Fallback (should never reach here)
    return _original_build_system_prompt(char_dict, _commit_to_dict(commit) if commit else {})


def chat_once_unified(
    client: Any,
    model: str,
    messages: List[Dict[str, str]],
) -> str:
    """Unified chat function wrapping the original chat_once."""
    logger.debug("chat_once_unified: model=%s messages=%d", model, len(messages))
    response = client.chat(model=model, messages=messages)
    return response["message"]["content"].strip()


def get_ollama_client(host: Optional[str] = None) -> Any:
    """Create an Ollama client with configured host."""
    host = host or OLLAMA_HOST
    try:
        client = create_ollama_client(host)
        logger.info("Created Ollama client at %s", host)
        return client
    except SystemExit as exc:
        logger.warning("Ollama client creation failed: %s", exc)
        raise RuntimeError("Ollama Python client not available or host unreachable") from exc


def list_available_models(host: Optional[str] = None) -> List[str]:
    """List available Ollama models."""
    client = get_ollama_client(host)
    return get_available_models(client, host or OLLAMA_HOST)


def create_conversation(
    db: Session,
    project_id: int,
    character_ids: List[int],
    commit_id: Optional[int] = None,
    mode: str = "story-locked",
    title: Optional[str] = None,
) -> Conversation:
    """Factory for creating a new Conversation record."""
    characters = db.query(Character).filter(Character.id.in_(character_ids)).all()
    if not characters:
        raise ValueError("No valid characters found for conversation")

    if not title:
        names = ", ".join(c.name for c in characters)
        commit_label = ""
        if commit_id:
            commit = db.query(Commit).filter(Commit.id == commit_id).first()
            if commit:
                commit_label = f" at {commit.title or commit.commit_id}"
        title = f"Chat with {names}{commit_label}"

    conv = Conversation(
        project_id=project_id,
        commit_id=commit_id,
        mode=mode,
        title=title,
        messages=[],
    )
    conv.characters = characters
    db.add(conv)
    db.commit()
    db.refresh(conv)
    logger.info("Created conversation %s for project %s", conv.id, project_id)
    return conv


def build_chat_messages(
    character: Character,
    commit: Optional[Commit] = None,
    history: Optional[List[Dict[str, str]]] = None,
    mode: str = "story-locked",
    extra_system_contexts: Optional[List[str]] = None,
    all_commits: Optional[List[Commit]] = None,
    other_characters: Optional[List[Tuple[Character, Optional[Commit]]]] = None,
) -> List[Dict[str, str]]:
    """Build the message list for an LLM chat turn."""
    system_prompt = build_system_prompt(
        character,
        commit=commit,
        mode=mode,
        all_commits=all_commits,
        other_characters=other_characters,
    )
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    if extra_system_contexts:
        for context in extra_system_contexts:
            cleaned = context.strip() if context else ""
            if cleaned:
                messages.append({"role": "system", "content": cleaned})

    if history:
        messages.extend(history)

    return messages


def run_chat_turn(
    db: Session,
    request: ChatRequest,
    client: Any,
    model: str,
    lore_context: Optional[str] = None,
) -> ChatResponse:
    """Execute one chat turn: load conversation, build messages, call LLM, store response."""
    from backend.services.rag_service import search_lore  # deferred import to avoid circular

    # Load or create conversation
    if request.conversation_id:
        conv = db.query(Conversation).filter(Conversation.id == request.conversation_id).first()
        if not conv:
            raise ValueError(f"Conversation {request.conversation_id} not found")
    else:
        conv = create_conversation(
            db=db,
            project_id=request.project_id,
            character_ids=request.character_ids,
            commit_id=request.commit_id,
            mode=request.mode,
        )

    # Load characters
    characters = db.query(Character).filter(Character.id.in_(request.character_ids)).all()
    if not characters:
        raise ValueError("No characters found")

    primary_character = characters[0]
    commit = None
    if request.commit_id:
        commit = db.query(Commit).filter(Commit.id == request.commit_id).first()

    # For multi-character mode, gather other characters
    other_characters: Optional[List[Tuple[Character, Optional[Commit]]]] = None
    if request.mode == "multi-character" and len(characters) > 1:
        other_characters = []
        for char in characters[1:]:
            char_commit = None
            if request.commit_id:
                char_commit = db.query(Commit).filter(
                    Commit.character_id == char.id,
                    Commit.id == request.commit_id,
                ).first()
            other_characters.append((char, char_commit))

    # For post-end mode, load all commits for primary character
    all_commits: Optional[List[Commit]] = None
    if request.mode == "post-end":
        all_commits = (
            db.query(Commit)
            .filter(Commit.character_id == primary_character.id)
            .order_by(Commit.order_index)
            .all()
        )

    # RAG lore context
    extra_system_contexts: List[str] = []
    if lore_context:
        extra_system_contexts.append(lore_context)
    elif request.mode not in {"agent", "casual"}:
        # Attempt lightweight lore retrieval
        try:
            matches = search_lore(
                request.message,
                project_id=request.project_id,
                n_results=3,
            )
            if matches:
                lines = [
                    "Relevant retrieved lore follows.",
                    "Use it when it helps answer faithfully. Do not mention retrieval, files, or hidden context.",
                ]
                for idx, match in enumerate(matches, start=1):
                    meta = match.get("metadata", {})
                    source = meta.get("source_file", "unknown")
                    lines.append(f"Lore chunk {idx} ({source}):")
                    lines.append(match.get("text", "").strip())
                extra_system_contexts.append("\n".join(lines))
        except Exception as exc:
            logger.warning("Lore retrieval failed: %s", exc)

    # Build messages
    history = conv.messages or []
    # Convert ConversationMessage dicts to plain role/content dicts for the LLM
    plain_history = [{"role": m["role"], "content": m["content"]} for m in history]

    messages = build_chat_messages(
        character=primary_character,
        commit=commit,
        history=plain_history,
        mode=request.mode,
        extra_system_contexts=extra_system_contexts or None,
        all_commits=all_commits,
        other_characters=other_characters,
    )
    messages.append({"role": "user", "content": request.message})

    # Log prompt construction for debuggability
    logger.debug("Prompt dump for conv=%s mode=%s chars=%s", conv.id, request.mode, [c.name for c in characters])
    for i, msg in enumerate(messages):
        preview = msg["content"][:120].replace("\n", " ")
        logger.debug("  msg[%d] role=%s content=%s...", i, msg["role"], preview)

    # Call LLM
    assistant_text = chat_once_unified(client, model, messages)

    # Store messages
    user_msg: Dict[str, Any] = {"role": "user", "content": request.message}
    assistant_msg: Dict[str, Any] = {
        "role": "assistant",
        "content": assistant_text,
        "character_id": primary_character.id,
        "character_name": primary_character.name,
    }
    updated = list(history) + [user_msg, assistant_msg]
    conv.messages = updated
    db.commit()

    knowledge_gate_active = request.mode in {"story-locked", "post-end", "multi-character"}

    return ChatResponse(
        conversation_id=conv.id,
        message=ConversationMessage(
            role="assistant",
            content=assistant_text,
            character_id=primary_character.id,
            character_name=primary_character.name,
        ),
        mode=request.mode,
        knowledge_gate_active=knowledge_gate_active,
    )
