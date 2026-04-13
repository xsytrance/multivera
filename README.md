# MultiVera

Simple terminal conversation engine for story characters with temporal knowledge gating.

## What it does

- Loads a character JSON from `characters/`
- Loads a story commit JSON from `commits/`
- Builds one system prompt at session start
- Chats through the Python `ollama` package
- Keeps conversation history in memory for the current terminal session

## Run

From the workspace root:

```bash
multivera/.venv/bin/python multivera/engine.py
```

Or from inside `multivera/`:

```bash
.venv/bin/python engine.py
```

## Options

```bash
multivera/.venv/bin/python multivera/engine.py \
  --character manus \
  --commit people_of_pisces \
  --model llama3.1:8b \
  --host http://100.94.216.114:11434
```

## File layout

```text
multivera/
├── README.md
├── engine.py
├── .gitignore
├── characters/
│   └── manus.json
└── commits/
    └── people_of_pisces.json
```

## Character JSON shape

```json
{
  "name": "Character Name",
  "title": "Optional Title",
  "origin": "Where they are from",
  "physical": "Physical description",
  "items": ["Important item 1", "Important item 2"],
  "personality": "Core personality",
  "speech_style": "How they speak",
  "never_does": "Hard rule for behavior"
}
```

## Commit JSON shape

```json
{
  "commit_id": "story_checkpoint_id",
  "title": "Checkpoint title",
  "location": "Current location",
  "situation": "What is happening right now",
  "knows": [
    "Facts the character knows at this point"
  ],
  "does_not_know": [
    "Facts the character must not reveal or know yet"
  ]
}
```

## Adding more characters or commits

Duplicate an existing JSON file, rename it, and update the fields.

Examples:

```bash
multivera/.venv/bin/python multivera/engine.py --character manus --commit people_of_pisces
multivera/.venv/bin/python multivera/engine.py --character another_character --commit later_scene
```

## Hackermouth lore ingestion

Drop `.docx` lore files into `knowledge/hackermouth/`, then ingest them into the local ChromaDB collection:

```bash
.venv/bin/python feed_hackermouth.py
```

This rebuilds the `hackermouth_lore` collection in local storage under `.chroma/`.

## Telegram bot

There is also a Telegram bot entrypoint for Hackermouth that uses the same character JSON voice rules and Ollama endpoint logic as `engine.py`, plus the top 3 relevant lore chunks from the `hackermouth_lore` ChromaDB collection on every message.

Run it from inside `multivera/` after installing `python-telegram-bot` and setting your bot token:

```bash
export TELEGRAM_BOT_TOKEN=your_bot_token_here
.venv/bin/python hackermouth_telegram_bot.py
```

Optional environment variables:

- `OLLAMA_HOST` (defaults to `http://100.94.216.114:11434`)
- `OLLAMA_MODEL` (defaults to `llama3.1:8b`)
- `MULTIVERA_CHARACTER` (defaults to `hackermouth`)
- `MULTIVERA_COMMIT` (defaults to `hackermouth_active`)

Commands:

- `/start` to begin
- `/reset` to clear per-chat conversation history

## Notes

- The Python client connects to the remote Ollama host directly.
- For the Python `ollama` package, use the Ollama server root URL, not the OpenAI-compatible `/v1` path.
- Type `exit` or `quit` to leave the chat loop.
