from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, Any

try:
    from telegram import Update
    from telegram.constants import ChatAction
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
except ModuleNotFoundError:
    Update = Any
    ChatAction = Any
    Application = Any
    CommandHandler = Any
    ContextTypes = Any
    MessageHandler = Any
    filters = Any

from engine import (
    DEFAULT_HOST,
    DEFAULT_MODEL,
    chat_once,
    create_ollama_client,
    get_available_models,
    load_character_and_commit,
)
from hackermouth_rag import COLLECTION_NAME, search_lore
from storage import load_chat_history, save_chat_history

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("hackermouth.telegram")

if TYPE_CHECKING:
    from telegram.ext import Application as TelegramApplication

DEFAULT_CHARACTER = "hackermouth"
DEFAULT_COMMIT = "hackermouth_active"
MAX_HISTORY_MESSAGES = 12
LORE_RESULT_COUNT = 1


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def trim_history(history: list[dict[str, str]]) -> None:
    if len(history) > MAX_HISTORY_MESSAGES:
        del history[:-MAX_HISTORY_MESSAGES]


def build_lore_context(user_text: str) -> str | None:
    matches = search_lore(user_text, n_results=LORE_RESULT_COUNT)
    if not matches:
        return None

    passage = (matches[0].get("text") or "").strip()
    if not passage:
        return None
    return (
        "Thin bleed-through from a deeper reel — rumor and static, not gospel:\n\n"
        f"{passage}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        "Hackermouth is listening through the tape. Send a message."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    if chat_id is not None:
        save_chat_history(chat_id, [])
    await update.message.reply_text("The tape hisses clean. The signal begins again.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or not update.message.text:
        return

    chat_id = update.effective_chat.id
    if chat_id is None:
        return

    history = load_chat_history(chat_id)
    user_text = update.message.text.strip()
    if not user_text:
        return

    await context.bot.send_chat_action(
        chat_id=chat_id,
        action=ChatAction.TYPING,
    )

    try:
        lore_context = build_lore_context(user_text)
        extra_system_contexts = [lore_context] if lore_context else None
        response_text = chat_once(
            context.application.bot_data["ollama_client"],
            context.application.bot_data["ollama_model"],
            context.application.bot_data["character"],
            context.application.bot_data["commit"],
            user_text,
            history=history,
            extra_system_contexts=extra_system_contexts,
        )
    except Exception:
        logger.exception("Hackermouth failed to answer")
        await update.message.reply_text("The tape stutters. Hackermouth does not surface.")
        return

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": response_text})
    trim_history(history)
    save_chat_history(chat_id, history)

    await update.message.reply_text(response_text)


def build_application() -> "TelegramApplication":
    try:
        from telegram.ext import Application, CommandHandler, MessageHandler, filters
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: python-telegram-bot. Install it with pip install python-telegram-bot."
        ) from exc

    token = get_required_env("TELEGRAM_BOT_TOKEN")
    ollama_host = os.getenv("OLLAMA_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    ollama_model = os.getenv("OLLAMA_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    character_name = os.getenv("MULTIVERA_CHARACTER", DEFAULT_CHARACTER).strip() or DEFAULT_CHARACTER
    commit_name = os.getenv("MULTIVERA_COMMIT", DEFAULT_COMMIT).strip() or DEFAULT_COMMIT

    character, commit = load_character_and_commit(character_name, commit_name)
    ollama_client = create_ollama_client(ollama_host)
    available_models = get_available_models(ollama_client, ollama_host)
    if ollama_model not in available_models:
        raise SystemExit(
            f"Requested model '{ollama_model}' was not found on {ollama_host}. "
            f"Available models: {', '.join(available_models)}"
        )

    application = Application.builder().token(token).build()
    application.bot_data.update(
        {
            "character": character,
            "commit": commit,
            "ollama_client": ollama_client,
            "ollama_model": ollama_model,
        }
    )
    logger.info("Hackermouth lore collection ready: %s", COLLECTION_NAME)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application


def main() -> None:
    application = build_application()
    logger.info("Hackermouth Telegram bot is live")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
