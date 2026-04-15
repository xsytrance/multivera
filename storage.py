from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("hackermouth.storage")

CHATS_DIR = Path(__file__).resolve().parent / "data" / "chats"


def _chat_path(chat_id: int) -> Path:
    return CHATS_DIR / f"{chat_id}.json"


def load_chat_history(chat_id: int) -> list[dict[str, str]]:
    path = _chat_path(chat_id)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unreadable chat history %s: %s", path, exc)
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        role, content = item.get("role"), item.get("content")
        if isinstance(role, str) and isinstance(content, str):
            out.append({"role": role, "content": content})
    return out


def save_chat_history(chat_id: int, history: list[dict[str, str]]) -> None:
    path = _chat_path(chat_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
