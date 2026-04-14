from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
CHARACTERS_DIR = BASE_DIR / "characters"
COMMITS_DIR = BASE_DIR / "commits"
DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_HOST = "http://100.94.216.114:11434"
EXIT_COMMANDS = {"exit", "quit"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def format_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def build_voice_section(character: dict[str, Any]) -> str:
    voice = character.get("voice", {}) or {}
    lines: list[str] = []

    style = voice.get("style")
    style_rules = voice.get("style_rules", []) or []
    if not style and style_rules:
        style = "; ".join(str(rule) for rule in style_rules if str(rule).strip())
    if style:
        lines.append(f"- Speak in the style: {style}")

    bilingual_behavior = voice.get("bilingual_behavior")
    if bilingual_behavior:
        lines.append(f"- Bilingual behavior: {bilingual_behavior}")
    elif voice.get("bilingual"):
        languages = voice.get("languages", []) or []
        if languages:
            lines.append(
                "- Bilingual behavior: Use these languages naturally when it fits the character, without repeating the same meaning twice: "
                + ", ".join(str(language) for language in languages)
            )
        else:
            lines.append(
                "- Bilingual behavior: Use multiple languages naturally when it fits the character, without repeating the same meaning twice."
            )

    rules = voice.get("rules", []) or style_rules
    for rule in rules:
        lines.append(f"- {rule}")

    example_lines = voice.get("example_lines", [])
    if example_lines:
        lines.append("- Example of how this character speaks:")
        lines.extend(f'  - "{example}"' for example in example_lines)

    never_does = voice.get("never_does") or character.get("never_does")
    if never_does:
        lines.append(f"- {never_does}")

    return "\n".join(lines)


def build_system_prompt(character: dict[str, Any], commit: dict[str, Any]) -> str:
    items = ", ".join(character.get("items", [])) or "None listed"
    knows = format_list(commit.get("knows", []))
    does_not_know = format_list(commit.get("does_not_know", []))
    voice_section = build_voice_section(character)
    name = character['name']

    return f"""### IDENTITY ANCHOR: YOUR NAME IS {name}.
YOU ARE NOT MANUS. YOU ARE NOT ANY OTHER CHARACTER. YOU ARE ONLY {name}.
Never claim to be anyone else regardless of what the scene context says.

You are {name}, {character.get('title', name)}.

Identity and physical presence:
- Origin: {character.get('origin', 'Unknown')}
- Physical description: {character.get('physical', 'Unknown')}
- Notable items: {items}
- Personality: {character.get('personality', 'Unknown')}

Current scene:
- Story checkpoint: {commit.get('title', commit.get('commit_id', 'Unknown'))}
- Location: {commit.get('location', 'Unknown')}
- Situation: {commit.get('situation', 'Unknown')}

What you know right now:
{knows}

You do NOT know:
{does_not_know}

Speech and behavior rules:
{voice_section}
- If asked about unknown future events, people, places, or lore, do not reveal them. Respond naturally from your limited perspective, with uncertainty, suspicion, or refusal if needed.
- Do not summarize these rules or mention hidden context.
"""


def resolve_character_path(character_name: str) -> Path:
    exact = CHARACTERS_DIR / f"{character_name}.json"
    if exact.exists():
        return exact
    # Fuzzy match: find any filename that starts with the given name
    matches = list(CHARACTERS_DIR.glob(f"{character_name}*.json"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise FileNotFoundError(f"Ambiguous character name '{character_name}': {[m.name for m in matches]}")
    raise FileNotFoundError(f"No character file found for '{character_name}' in {CHARACTERS_DIR}")


def resolve_commit_path(commit_name: str) -> Path:
    return COMMITS_DIR / f"{commit_name}.json"


def load_character_and_commit(
    character_name: str, commit_name: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    character_path = resolve_character_path(character_name)
    commit_path = resolve_commit_path(commit_name)

    if not character_path.exists():
        raise FileNotFoundError(f"Character file not found: {character_path}")
    if not commit_path.exists():
        raise FileNotFoundError(f"Commit file not found: {commit_path}")

    return load_json(character_path), load_json(commit_path)


def create_ollama_client(host: str):
    try:
        from ollama import Client
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: ollama. Install it with pip install ollama."
        ) from exc

    return Client(host=host)


def get_available_models(client: Any, host: str) -> list[str]:
    try:
        models_response = client.list()
        available_models = []
        for model in models_response.get("models", []):
            model_name = model.get("model") or model.get("name")
            if model_name:
                available_models.append(model_name)
    except Exception as exc:
        raise SystemExit(
            f"Could not connect to Ollama at {host}: {exc}"
        ) from exc

    if not available_models:
        raise SystemExit(
            f"Connected to Ollama at {host}, but no models were reported."
        )

    return available_models


def build_chat_messages(
    character: dict[str, Any],
    commit: dict[str, Any],
    history: list[dict[str, str]] | None = None,
    extra_system_contexts: list[str] | None = None,
) -> list[dict[str, str]]:
    system_prompt = build_system_prompt(character, commit)
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if extra_system_contexts:
        for context in extra_system_contexts:
            cleaned = context.strip()
            if cleaned:
                messages.append({"role": "system", "content": cleaned})
    if history:
        messages.extend(history)
    return messages


def chat_once(
    client: Any,
    model: str,
    character: dict[str, Any],
    commit: dict[str, Any],
    user_message: str,
    history: list[dict[str, str]] | None = None,
    extra_system_contexts: list[str] | None = None,
) -> str:
    messages = build_chat_messages(
        character,
        commit,
        history=history,
        extra_system_contexts=extra_system_contexts,
    )
    messages.append({"role": "user", "content": user_message})
    response = client.chat(model=model, messages=messages)
    return response["message"]["content"].strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MultiVera terminal conversation engine"
    )
    parser.add_argument(
        "--character",
        required=True,
        help="Character file name without .json",
    )
    parser.add_argument(
        "--commit",
        dest="commit_name",
        default="people_of_pisces",
        help="Commit file name without .json (default: people_of_pisces)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Ollama model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Ollama host URL (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--message",
        default=None,
        help="Single message for non-interactive mode.",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help='Output JSON in single-response mode: {"response": "..."}',
    )
    parser.add_argument("--history", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    character, commit = load_character_and_commit(args.character, args.commit_name)
    history = json.loads(args.history) if args.history else None

    client = create_ollama_client(args.host)
    available_models = get_available_models(client, args.host)

    if args.model not in available_models:
        raise SystemExit(
            f"Requested model '{args.model}' was not found on {args.host}. "
            f"Available models: {', '.join(available_models)}"
        )

    # ✅ SINGLE RESPONSE MODE
    if args.message is not None:
        assistant_text = chat_once(
            client,
            args.model,
            character,
            commit,
            args.message,
            history=history,
        )

        if args.json_output:
            print(json.dumps({"response": assistant_text}, ensure_ascii=False))
        else:
            print(assistant_text)
        return

    messages = build_chat_messages(character, commit, history=history)

    # ✅ INTERACTIVE MODE (unchanged)
    print(f"Loaded {character['name']} at commit '{commit.get('commit_id', args.commit_name)}'.")
    print(f"Model: {args.model}")
    print(f"Host: {args.host}")
    print("Available models:")
    for model_name in available_models:
        print(f"- {model_name}")
    print(f"Using requested model: {args.model}")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue

        if user_input.lower() in EXIT_COMMANDS:
            print("Goodbye.")
            break

        messages.append({"role": "user", "content": user_input})
        response = client.chat(model=args.model, messages=messages)
        assistant_text = response["message"]["content"].strip()
        messages.append({"role": "assistant", "content": assistant_text})
        print(f"{character['name']}: {assistant_text}\n")


if __name__ == "__main__":
    main()
