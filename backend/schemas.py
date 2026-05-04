"""MultiVera Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Shared ───────────────────────────────────────────────────────────────────

class APIResponse(BaseModel):
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None


# ── Project ──────────────────────────────────────────────────────────────────

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sources: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    character_count: int = 0
    commit_count: int = 0


# ── Character ─────────────────────────────────────────────────────────────────

class CharacterBase(BaseModel):
    slug: str
    name: str
    role: Optional[str] = None
    affiliation: Optional[str] = None
    origin: Optional[str] = None
    appearance: Optional[str] = None
    personality: List[str] = Field(default_factory=list)
    tone: Optional[str] = None
    languages: List[str] = Field(default_factory=list)
    speech_patterns: Dict[str, Any] = Field(default_factory=dict)
    relationships: Dict[str, Any] = Field(default_factory=dict)
    notable_quotes: List[str] = Field(default_factory=list)
    weapons_tools: List[str] = Field(default_factory=list)
    backstory_summary: Optional[str] = None
    roleplay_instructions: Optional[str] = None
    knowledge_gates: Dict[str, Any] = Field(default_factory=dict)
    is_player: bool = False
    is_active: bool = True
    extra: Dict[str, Any] = Field(default_factory=dict)


class CharacterCreate(CharacterBase):
    pass


class CharacterUpdate(BaseModel):
    slug: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    affiliation: Optional[str] = None
    origin: Optional[str] = None
    appearance: Optional[str] = None
    personality: Optional[List[str]] = None
    tone: Optional[str] = None
    languages: Optional[List[str]] = None
    speech_patterns: Optional[Dict[str, Any]] = None
    relationships: Optional[Dict[str, Any]] = None
    notable_quotes: Optional[List[str]] = None
    weapons_tools: Optional[List[str]] = None
    backstory_summary: Optional[str] = None
    roleplay_instructions: Optional[str] = None
    knowledge_gates: Optional[Dict[str, Any]] = None
    is_player: Optional[bool] = None
    is_active: Optional[bool] = None
    extra: Optional[Dict[str, Any]] = None


class CharacterOut(CharacterBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime


class CharacterListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    slug: str
    name: str
    role: Optional[str] = None
    is_active: bool = True


# ── Commit ────────────────────────────────────────────────────────────────────

class CommitBase(BaseModel):
    commit_id: str
    title: Optional[str] = None
    location: Optional[str] = None
    situation: Optional[str] = None
    knows: List[str] = Field(default_factory=list)
    does_not_know: List[str] = Field(default_factory=list)
    chapter: Optional[str] = None
    scene: Optional[str] = None
    order_index: int = 0
    is_start: bool = False
    is_end: bool = False
    extra: Dict[str, Any] = Field(default_factory=dict)


class CommitCreate(CommitBase):
    character_id: Optional[int] = None


class CommitUpdate(BaseModel):
    commit_id: Optional[str] = None
    title: Optional[str] = None
    location: Optional[str] = None
    situation: Optional[str] = None
    knows: Optional[List[str]] = None
    does_not_know: Optional[List[str]] = None
    chapter: Optional[str] = None
    scene: Optional[str] = None
    order_index: Optional[int] = None
    is_start: Optional[bool] = None
    is_end: Optional[bool] = None
    extra: Optional[Dict[str, Any]] = None


class CommitOut(CommitBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    character_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# ── Conversation ─────────────────────────────────────────────────────────────

class ConversationMessage(BaseModel):
    role: str
    content: str
    character_id: Optional[int] = None
    character_name: Optional[str] = None


class ConversationBase(BaseModel):
    project_id: int
    character_ids: List[int]
    commit_id: Optional[int] = None
    mode: str = "story-locked"
    title: Optional[str] = None


class ConversationCreate(ConversationBase):
    pass


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: int
    character_ids: List[int]
    commit_id: Optional[int] = None
    mode: str
    title: Optional[str] = None
    messages: List[ConversationMessage] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ── Chat ───────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    project_id: int
    character_ids: List[int]
    commit_id: Optional[int] = None
    mode: str = "story-locked"
    message: str


class ChatResponse(BaseModel):
    conversation_id: str
    message: ConversationMessage
    mode: str
    knowledge_gate_active: bool = True


# ── Export ─────────────────────────────────────────────────────────────────────

class PersonaExport(BaseModel):
    name: str
    system_prompt: str
    character_json: Dict[str, Any]
    commit_json: Optional[Dict[str, Any]] = None
    mode_rules: str
    version: str = "multivera-v1"


class SystemPromptOut(BaseModel):
    character_id: int
    character_name: str
    mode: str
    commit_id: Optional[int] = None
    system_prompt: str


# ── Ingestion ────────────────────────────────────────────────────────────────

class IngestStatus(BaseModel):
    project_id: int
    files_processed: int
    chunks_stored: int
    collection_name: str
    status: str


class TimelineBuildRequest(BaseModel):
    character_id: Optional[int] = None
    source_text: Optional[str] = None


# ── Lore Search ──────────────────────────────────────────────────────────────

class LoreMatch(BaseModel):
    text: str
    metadata: Dict[str, Any]
    distance: Optional[float] = None


class LoreSearchRequest(BaseModel):
    query: str
    n_results: int = 3
    character_id: Optional[int] = None
    commit_id: Optional[int] = None


# ── Location ─────────────────────────────────────────────────────────────────

class LocationBase(BaseModel):
    name: str
    description: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class LocationCreate(LocationBase):
    pass


class LocationOut(LocationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    created_at: datetime


# ── Faction ───────────────────────────────────────────────────────────────────

class FactionBase(BaseModel):
    name: str
    description: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class FactionCreate(FactionBase):
    pass


class FactionOut(FactionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    created_at: datetime


# ── Weapon ────────────────────────────────────────────────────────────────────

class WeaponBase(BaseModel):
    name: str
    description: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class WeaponCreate(WeaponBase):
    pass


class WeaponOut(WeaponBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    created_at: datetime
