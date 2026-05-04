"""MultiVera backend configuration."""
from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
DB_PATH = BACKEND_DIR / "multivera.db"
CHROMA_DIR = BASE_DIR / ".chroma"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
CHARACTERS_DIR = BASE_DIR / "characters"
COMMITS_DIR = BASE_DIR / "commits"
LOCATIONS_DIR = BASE_DIR / "locations"
FACTIONS_DIR = BASE_DIR / "factions"
WEAPONS_DIR = BASE_DIR / "weapons"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://100.94.216.114:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
DEFAULT_PROJECT_NAME = "Red Noodle Clan"

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100

# Ingestion settings
SUPPORTED_UPLOAD_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
MAX_UPLOAD_SIZE_MB = 50
