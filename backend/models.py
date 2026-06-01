"""MultiVera SQLAlchemy ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


# ── Association tables ───────────────────────────────────────────────────────

conversation_character_association = Table(
    "conversation_characters",
    Base.metadata,
    Column("conversation_id", String, ForeignKey("conversations.id", ondelete="CASCADE")),
    Column("character_id", Integer, ForeignKey("characters.id", ondelete="CASCADE")),
)


# ── Helper ───────────────────────────────────────────────────────────────────

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Project ──────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sources: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    save_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    characters: Mapped[List["Character"]] = relationship(
        "Character", back_populates="project", cascade="all, delete-orphan"
    )
    commits: Mapped[List["Commit"]] = relationship(
        "Commit", back_populates="project", cascade="all, delete-orphan"
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation", back_populates="project", cascade="all, delete-orphan"
    )
    lore_chunks: Mapped[List["LoreChunk"]] = relationship(
        "LoreChunk", back_populates="project", cascade="all, delete-orphan"
    )
    locations: Mapped[List["Location"]] = relationship(
        "Location", back_populates="project", cascade="all, delete-orphan"
    )
    factions: Mapped[List["Faction"]] = relationship(
        "Faction", back_populates="project", cascade="all, delete-orphan"
    )
    weapons: Mapped[List["Weapon"]] = relationship(
        "Weapon", back_populates="project", cascade="all, delete-orphan"
    )


# ── Character ────────────────────────────────────────────────────────────────

class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    affiliation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    origin: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    appearance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    personality: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    tone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    languages: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    speech_patterns: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    relationships: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    notable_quotes: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    weapons_tools: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    backstory_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    roleplay_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    knowledge_gates: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    is_player: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    project: Mapped["Project"] = relationship("Project", back_populates="characters")
    commits: Mapped[List["Commit"]] = relationship(
        "Commit", back_populates="character", cascade="all, delete-orphan"
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation",
        secondary=conversation_character_association,
        back_populates="characters",
    )


# ── Commit (Timeline Checkpoint) ─────────────────────────────────────────────

class Commit(Base):
    __tablename__ = "commits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    character_id: Mapped[Optional[int]] = mapped_column(ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    commit_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    situation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    knows: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    does_not_know: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    chapter: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    scene: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    order_index: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    is_start: Mapped[bool] = mapped_column(Boolean, default=False)
    is_end: Mapped[bool] = mapped_column(Boolean, default=False)
    extra: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    project: Mapped["Project"] = relationship("Project", back_populates="commits")
    character: Mapped[Optional["Character"]] = relationship("Character", back_populates="commits")


# ── Conversation ──────────────────────────────────────────────────────────────

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    commit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("commits.id", ondelete="SET NULL"), nullable=True)
    mode: Mapped[str] = mapped_column(String(50), default="story-locked")
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    project: Mapped["Project"] = relationship("Project", back_populates="conversations")
    characters: Mapped[List["Character"]] = relationship(
        "Character",
        secondary=conversation_character_association,
        back_populates="conversations",
    )


# ── LoreChunk ─────────────────────────────────────────────────────────────────

class LoreChunk(Base):
    __tablename__ = "lore_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    character_id: Mapped[Optional[int]] = mapped_column(ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    commit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("commits.id", ondelete="SET NULL"), nullable=True)
    source_file: Mapped[str] = mapped_column(String(500), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    extra: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    project: Mapped["Project"] = relationship("Project", back_populates="lore_chunks")


# ── Location ──────────────────────────────────────────────────────────────────

class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    project: Mapped["Project"] = relationship("Project", back_populates="locations")


# ── Faction ───────────────────────────────────────────────────────────────────

class Faction(Base):
    __tablename__ = "factions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    project: Mapped["Project"] = relationship("Project", back_populates="factions")


# ── Weapon ────────────────────────────────────────────────────────────────────

class Weapon(Base):
    __tablename__ = "weapons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    project: Mapped["Project"] = relationship("Project", back_populates="weapons")
