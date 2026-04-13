from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    from anthropic import Anthropic
except ModuleNotFoundError:
    Anthropic = None  # type: ignore[assignment]

try:
    from openai import OpenAI
except ModuleNotFoundError:
    OpenAI = None  # type: ignore[assignment]

BASE_DIR = Path(__file__).resolve().parent.parent
VERA_DIR = BASE_DIR / "vera"
CHARACTERS_DIR = BASE_DIR / "characters"
COMMITS_DIR = BASE_DIR / "commits"
ENV_PATH = VERA_DIR / ".env"
DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-5.3-codex"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


CHARACTER_SCHEMA_DESCRIPTION = """{
  \"name\": \"\",
  \"title\": \"\",
  \"universe\": \"\",
  \"origin\": \"\",
  \"physical\": \"\",
  \"items\": [],
  \"personality\": \"\",
  \"voice\": {
    \"style_rules\": [],
    \"example_lines\": [],
    \"bilingual\": false,
    \"languages\": []
  },
  \"never_does\": \"\"
}"""

COMMIT_SCHEMA_DESCRIPTION = """{
  \"commit_id\": \"\",
  \"title\": \"\",
  \"location\": \"\",
  \"situation\": \"\",
  \"knows\": [],
  \"does_not_know\": []
}"""


@dataclass
class ProviderConfig:
    provider: str
    model: str
    api_key: str
    base_url: str | None = None
    site_url: str | None = None
    app_name: str | None = None


class LLMClient:
    def create_json(self, prompt_text: str, retry_prompt: str | None = None) -> Any:
        raise NotImplementedError


class AnthropicLLMClient(LLMClient):
    def __init__(self, config: ProviderConfig) -> None:
        if Anthropic is None:
            raise SystemExit(
                "Missing dependency: anthropic. Install it with `pip install anthropic`."
            )
        self.client = Anthropic(api_key=config.api_key)
        self.model = config.model

    def _call(self, prompt_text: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt_text}],
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )

    def create_json(self, prompt_text: str, retry_prompt: str | None = None) -> Any:
        text = self._call(prompt_text)
        try:
            return parse_json_response(text)
        except json.JSONDecodeError:
            if retry_prompt is None:
                raise SystemExit("Model returned invalid JSON and no retry prompt was provided.")

        text = self._call(retry_prompt)
        try:
            return parse_json_response(text)
        except json.JSONDecodeError as exc:
            raise SystemExit(
                "Model returned invalid JSON twice. Please try again with clearer source text."
            ) from exc


class OpenAILLMClient(LLMClient):
    def __init__(self, config: ProviderConfig) -> None:
        if OpenAI is None:
            raise SystemExit(
                "Missing dependency: openai. Install it with `pip install openai`."
            )

        extra_headers: dict[str, str] = {}
        if config.provider == "openrouter":
            if config.site_url:
                extra_headers["HTTP-Referer"] = config.site_url
            if config.app_name:
                extra_headers["X-Title"] = config.app_name

        kwargs: dict[str, Any] = {
            "api_key": config.api_key,
            "base_url": config.base_url or DEFAULT_OPENAI_BASE_URL,
        }
        if extra_headers:
            kwargs["default_headers"] = extra_headers

        self.client = OpenAI(**kwargs)
        self.model = config.model

    def _call(self, prompt_text: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=prompt_text,
        )
        return getattr(response, "output_text", "") or ""

    def create_json(self, prompt_text: str, retry_prompt: str | None = None) -> Any:
        text = self._call(prompt_text)
        try:
            return parse_json_response(text)
        except json.JSONDecodeError:
            if retry_prompt is None:
                raise SystemExit("Model returned invalid JSON and no retry prompt was provided.")

        text = self._call(retry_prompt)
        try:
            return parse_json_response(text)
        except json.JSONDecodeError as exc:
            raise SystemExit(
                "Model returned invalid JSON twice. Please try again with clearer source text."
            ) from exc


def prompt(text: str) -> str:
    return input(text).strip()


def prompt_non_empty(text: str) -> str:
    while True:
        value = prompt(text)
        if value:
            return value
        print("Please enter a value.")


def prompt_int_in_range(text: str, minimum: int, maximum: int, default: int) -> int:
    while True:
        raw = prompt(text)
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            print(f"Please enter a number from {minimum} to {maximum}.")
            continue
        if minimum <= value <= maximum:
            return value
        print(f"Please enter a number from {minimum} to {maximum}.")


def prompt_multiline(text: str) -> str:
    print(text)
    print("Paste your text. Finish with a line containing only END.")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "character"


def extract_json_block(text: str) -> str:
    match = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    start_candidates = [idx for idx in (text.find("{"), text.find("[")) if idx != -1]
    if not start_candidates:
        return text.strip()

    start = min(start_candidates)
    end_object = text.rfind("}")
    end_array = text.rfind("]")
    end = max(end_object, end_array)
    if end >= start:
        return text[start : end + 1].strip()
    return text.strip()


def parse_json_response(text: str) -> Any:
    return json.loads(extract_json_block(text))


def ensure_dependencies(provider: str) -> None:
    missing = ["python-dotenv"]
    try:
        import dotenv  # noqa: F401
        missing = []
    except ModuleNotFoundError:
        pass

    if provider == "anthropic" and Anthropic is None:
        missing.append("anthropic")
    if provider in {"openai", "openrouter"} and OpenAI is None:
        missing.append("openai")

    if missing:
        unique = ", ".join(sorted(set(missing)))
        raise SystemExit(
            f"Missing dependencies: {unique}. Install them with `pip install anthropic openai python-dotenv`."
        )


def load_provider_config() -> ProviderConfig:
    load_dotenv(ENV_PATH, override=True)

    provider = os.getenv("VERA_PROVIDER", DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
    model = os.getenv("VERA_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise SystemExit(
                "Missing ANTHROPIC_API_KEY. Add it to multivera/vera/.env like this:\n"
                "ANTHROPIC_API_KEY=your_key_here"
            )
        return ProviderConfig(provider=provider, model=model, api_key=api_key)

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise SystemExit(
                "Missing OPENAI_API_KEY. Add it to multivera/vera/.env like this:\n"
                "OPENAI_API_KEY=your_key_here"
            )
        base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip() or DEFAULT_OPENAI_BASE_URL
        return ProviderConfig(provider=provider, model=model, api_key=api_key, base_url=base_url)

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise SystemExit(
                "Missing OPENROUTER_API_KEY. Add it to multivera/vera/.env like this:\n"
                "OPENROUTER_API_KEY=your_key_here"
            )
        base_url = os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).strip() or DEFAULT_OPENROUTER_BASE_URL
        site_url = os.getenv("OPENROUTER_SITE_URL", "https://openclaw.ai").strip() or None
        app_name = os.getenv("OPENROUTER_APP_NAME", "MultiVera VERA").strip() or None
        return ProviderConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            site_url=site_url,
            app_name=app_name,
        )

    raise SystemExit(
        "Unsupported VERA_PROVIDER. Use one of: openai, openrouter, anthropic."
    )


def build_client(config: ProviderConfig) -> LLMClient:
    if config.provider == "anthropic":
        return AnthropicLLMClient(config)
    if config.provider in {"openai", "openrouter"}:
        return OpenAILLMClient(config)
    raise SystemExit(f"Unsupported provider: {config.provider}")


def normalize_character(character: dict[str, Any]) -> dict[str, Any]:
    voice = character.get("voice", {}) or {}
    style_rules = voice.get("style_rules", []) or []
    languages = voice.get("languages", []) or []

    normalized_voice = {
        "rules": style_rules,
        "example_lines": voice.get("example_lines", []) or [],
        "bilingual": bool(voice.get("bilingual", False)),
        "languages": languages,
    }

    if normalized_voice["bilingual"] and languages:
        normalized_voice["bilingual_behavior"] = (
            "Use the listed languages naturally when it fits the character, but never self-translate the same line twice. "
            f"Languages: {', '.join(str(lang) for lang in languages)}."
        )

    return {
        "name": character.get("name", "Unknown Character"),
        "title": character.get("title", ""),
        "universe": character.get("universe", ""),
        "origin": character.get("origin", ""),
        "physical": character.get("physical", ""),
        "items": character.get("items", []) or [],
        "personality": character.get("personality", ""),
        "voice": normalized_voice,
        "never_does": character.get("never_does", ""),
    }


def save_character(character: dict[str, Any]) -> Path:
    normalized = normalize_character(character)
    file_name = slugify(str(normalized["name"])) + ".json"
    path = CHARACTERS_DIR / file_name
    path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def save_commit(commit: dict[str, Any]) -> Path:
    commit_id = slugify(str(commit.get("commit_id", "commit")))
    commit["commit_id"] = commit_id
    path = COMMITS_DIR / f"{commit_id}.json"
    path.write_text(json.dumps(commit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def generate_well_known_character(client: LLMClient) -> list[dict[str, Any]]:
    story = prompt_non_empty("Story/universe name: ")
    character_name = prompt_non_empty("Character name: ")

    prompt_text = f"""You are a story analyst for a character simulation engine.
Research the character {character_name} from {story}.
Generate a MultiVera character JSON and suggest 3 commit points.
Use `universe` for the story or setting name, and use `origin` for the character's birthplace, hometown, region, or native place inside the story world, not the franchise title.
Output ONLY valid JSON in this exact format:
{{
  \"character\": {CHARACTER_SCHEMA_DESCRIPTION},
  \"suggested_commits\": [
    {COMMIT_SCHEMA_DESCRIPTION},
    {COMMIT_SCHEMA_DESCRIPTION},
    {COMMIT_SCHEMA_DESCRIPTION}
  ]
}}"""

    retry_prompt = prompt_text + "\nReturn raw JSON only. No markdown fences, no commentary, no prose."
    payload = client.create_json(prompt_text, retry_prompt)

    if not isinstance(payload, dict) or "character" not in payload or "suggested_commits" not in payload:
        raise SystemExit("Model returned JSON, but it did not match the expected well-known story format.")

    character = payload["character"]
    commits = payload["suggested_commits"]
    if not isinstance(character, dict) or not isinstance(commits, list):
        raise SystemExit("Model returned malformed character or commit data.")

    character["_suggested_commits"] = commits
    return [character]


def generate_custom_characters(client: LLMClient) -> list[dict[str, Any]]:
    question_limit = prompt_int_in_range(
        "How many clarifying questions are you willing to answer? (0-10, default 3): ",
        0,
        10,
        3,
    )

    story_text = ""
    while not story_text:
        story_text = prompt_multiline("Paste your story text for VERA.")
        if not story_text:
            print("Story text was empty. Please paste it again.")

    base_prompt = f"""You are a story analyst for a character simulation engine.
Read this story text and extract ALL characters you can identify.
Use `universe` for the story or setting name, and use `origin` for each character's birthplace, hometown, region, or native place inside the story world when known.
If anything is ambiguous and the question limit allows, ask the user up to {question_limit} clarifying questions total.
If the limit is 0, do your absolute best with the available text only.
Output ONLY valid JSON in this exact format:
{{
  \"questions\": [\"question 1\", \"question 2\"],
  \"characters\": [
    {CHARACTER_SCHEMA_DESCRIPTION}
  ]
}}

Story text:
{story_text}
"""

    retry_prompt = base_prompt + "\nReturn raw JSON only. No markdown fences, no explanation."
    payload = client.create_json(base_prompt, retry_prompt)

    if not isinstance(payload, dict):
        raise SystemExit("Model returned malformed JSON for custom story analysis.")

    questions = payload.get("questions", []) or []
    characters = payload.get("characters", []) or []

    answers: list[dict[str, str]] = []
    if question_limit > 0 and questions:
        for raw_question in questions[:question_limit]:
            question = str(raw_question).strip()
            if not question:
                continue
            answer = prompt_non_empty(f"Clarifying question: {question}\n> ")
            answers.append({"question": question, "answer": answer})

        follow_up_prompt = f"""You are a story analyst for a character simulation engine.
You already reviewed this story text:
{story_text}

You asked these clarifying questions and received these answers:
{json.dumps(answers, indent=2, ensure_ascii=False)}

Now generate the final character extraction.
Output ONLY valid JSON in this exact format:
{{
  \"characters\": [
    {CHARACTER_SCHEMA_DESCRIPTION}
  ]
}}
"""
        retry_follow_up = follow_up_prompt + "\nReturn raw JSON only. No markdown fences, no explanation."
        payload = client.create_json(follow_up_prompt, retry_follow_up)
        if not isinstance(payload, dict):
            raise SystemExit("Model returned malformed JSON after clarifying questions.")
        characters = payload.get("characters", []) or []

    if not isinstance(characters, list) or not characters:
        raise SystemExit("No characters were generated from the provided story text.")

    return [character for character in characters if isinstance(character, dict)]


def generate_commits_for_character(client: LLMClient, character: dict[str, Any]) -> list[dict[str, Any]]:
    character_json = json.dumps(character, indent=2, ensure_ascii=False)
    prompt_text = f"""Based on this character's story arc, suggest 3 commit points representing major knowledge shifts.
For each generate a commit JSON in this format:
{COMMIT_SCHEMA_DESCRIPTION}
Output ONLY valid JSON array of 3 commits.

Character JSON:
{character_json}
"""
    retry_prompt = prompt_text + "\nReturn raw JSON only. No markdown fences, no explanation."
    commits = client.create_json(prompt_text, retry_prompt)

    if not isinstance(commits, list) or len(commits) != 3:
        raise SystemExit("Model did not return a valid JSON array of 3 commits.")
    return [commit for commit in commits if isinstance(commit, dict)]


def ask_yes_no(text: str, default: bool = False) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        raw = prompt(text + suffix).lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please answer yes or no.")


def maybe_launch_engine(character_path: Path, commits: list[dict[str, Any]]) -> None:
    if not commits:
        print("No commit files were available to launch a chat.")
        return

    if not ask_yes_no("Would you like to chat with this character now?"):
        return

    first_commit_id = str(commits[0].get("commit_id", "")).strip()
    if not first_commit_id:
        print("Could not determine the first commit to launch.")
        return

    print("Launching MultiVera engine...\n")
    subprocess.run(
        [
            "python3",
            str(BASE_DIR / "engine.py"),
            "--character",
            character_path.stem,
            "--commit",
            first_commit_id,
        ],
        check=False,
        cwd=BASE_DIR,
    )


def main() -> None:
    config = load_provider_config()
    ensure_dependencies(config.provider)
    client = build_client(config)

    CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
    COMMITS_DIR.mkdir(parents=True, exist_ok=True)
    VERA_DIR.mkdir(parents=True, exist_ok=True)

    print("Welcome to VERA — MultiVera Prep Tool")
    print(f"Provider: {config.provider}")
    print(f"Model: {config.model}")
    print("Is this a well-known published story or a personal/custom story?")
    print("[1] Well-known (VERA will research automatically)")
    print("[2] Personal/Custom (VERA reads text you provide)")

    story_type = ""
    while story_type not in {"1", "2"}:
        story_type = prompt("> ")
        if story_type not in {"1", "2"}:
            print("Please enter 1 or 2.")

    if story_type == "1":
        characters = generate_well_known_character(client)
    else:
        characters = generate_custom_characters(client)

    saved_character_paths: list[Path] = []
    character_commits: dict[str, list[dict[str, Any]]] = {}

    for character in characters:
        character_path = save_character(character)
        saved_character_paths.append(character_path)
        print(f"Saved character JSON: {character_path}")

        commits = character.pop("_suggested_commits", None)
        if not commits:
            commits = generate_commits_for_character(client, character)

        saved_commits: list[dict[str, Any]] = []
        for commit in commits:
            saved_path = save_commit(commit)
            saved_commits.append(commit)
            print(f"Saved commit JSON: {saved_path}")

        character_commits[character_path.stem] = saved_commits

    if not saved_character_paths:
        print("No characters were saved.")
        return

    launch_target = saved_character_paths[0]
    if len(saved_character_paths) > 1:
        print("Generated characters:")
        for index, path in enumerate(saved_character_paths, start=1):
            print(f"[{index}] {path.stem}")
        selection = prompt_int_in_range(
            "Which character should be the launch target? (default 1): ",
            1,
            len(saved_character_paths),
            1,
        )
        launch_target = saved_character_paths[selection - 1]

    maybe_launch_engine(launch_target, character_commits.get(launch_target.stem, []))


if __name__ == "__main__":
    main()
