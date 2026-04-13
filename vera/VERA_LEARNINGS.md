# VERA Learnings & Automation Playbook

## Known Issues & Fixes

- **Anthropic-only first pass was too rigid**
  - Initial VERA version was hardwired to the Anthropic client.
  - Fix: refactored VERA into a modular provider layer.
  - Current supported providers: OpenAI, OpenRouter, Anthropic.
  - Current default: `openai` with `gpt-5.3-codex`.

- **Anthropic key validation failed because the account had no credits**
  - The key itself loaded correctly, but live API use returned insufficient credit errors.
  - Fix: switched default VERA provider to OpenAI so work could continue immediately.

- **Python deps were missing in the local venv**
  - `ollama`, `anthropic`, `python-dotenv`, and later `openai` were not initially available.
  - Fix: install packages into `multivera/.venv` instead of trying to mutate the system Python.

- **Ollama Python client should use server root, not `/v1`**
  - The engine failed against `http://100.94.216.114:11434/v1` with a 404.
  - Fix: use `http://100.94.216.114:11434` as the Ollama host for the Python client.

- **VERA used `origin` incorrectly for famous characters**
  - First Zoro run produced `origin: "One Piece"`, which is the franchise title, not birthplace.
  - Fix: add a separate `universe` field and reserve `origin` for birthplace, hometown, region, or native place in-world.

- **VERA duplicated voice data**
  - First generated characters stored both `voice.style` and `voice.rules`, duplicating the same content.
  - Fix: remove `voice.style` from VERA-generated character JSON and keep `voice.rules` as the source of truth.

- **Engine prompt duplicated style wording for VERA characters**
  - Because `voice.style` existed, the engine printed both a style summary and the same rules again.
  - Fix: after removing `voice.style` from VERA output, engine prompting no longer duplicates style content for VERA-generated characters.

- **Interactive terminal feeding can interleave visually when sending multiple lines fast**
  - In the custom story pipeline, rapid input caused prompt text and pasted story text to appear visually mashed together in terminal logs.
  - Fix: functionality still worked, but for debugging it is better to expect noisy terminal transcripts when batching interactive input programmatically.

- **VERA can over-infer or misassign canonical items**
  - Roz Kolora was initially given `Cuatroblade`, which belongs to Manus.
  - Fix: manually correct generated JSON when an item is relationally near a character but not actually theirs.

- **VERA can choose a scene/location instead of the broader story world for `universe`**
  - Roz Kolora was initially assigned `universe: "People of Pisces"`.
  - Fix: correct to `A Poetic Saga of the Red Noodle Clan` and tighten prompts around `universe` meaning.

## What Works Well

- **Knowledge gating works**
  - The core engine behavior is real, not theoretical.
  - Manus answered commit-specific questions differently depending on the selected story point.

- **Voice rules belong in character JSON, not code**
  - Moving voice tuning into character files was the right architecture.
  - It allows future refinement without touching `engine.py`.

- **Well-known story pipeline works end to end**
  - VERA successfully generated a full Zoro character plus 3 commits from a simple famous-character prompt.
  - It saved files automatically and offered to launch the engine afterward.

- **Custom story pipeline can extract multiple characters from a short passage**
  - A single Red Noodle Clan excerpt produced:
    - Roz Kolora
    - Manus Flatfoot
    - Highborn Atabey
    - Azula Sabra
    - Koden Bushi Bloodflower
    - Shield Doncellas
  - This is a strong sign that VERA can act as a character extraction layer, not just a single-character generator.

- **OpenAI `gpt-5.3-codex` works as a live backend for VERA**
  - API call test succeeded.
  - VERA ran end to end with OpenAI as provider.

## Voice Tuning Patterns

- **Generic output happens fast without hard limits**
  - Characters drift into exposition, stage directions, and decorative filler unless constrained.

- **Best voice rules are short, behavioral, and concrete**
  - Strong examples:
    - respond in 1 to 3 sentences maximum
    - no parenthetical stage directions
    - no quotation marks around responses
    - never over-explains
    - implies more than states

- **Example lines help a lot**
  - When example lines were added for Manus, output got closer to the intended voice immediately.
  - Example lines are especially useful for rhythm, compression, and tonal confidence.

- **Characters sound better when rules describe pressure, not aesthetics**
  - "Measured and deliberate" works better than vague descriptors like "poetic" alone.
  - "Every word earns its place" is stronger than generic requests for concision.

- **Even strong rules may still need post-generation cleanup**
  - Roz improved dramatically after voice tightening, but this should be expected as a recurring tuning loop.

## Well-Known Story Patterns

- VERA can generate usable famous-character scaffolds with very little user input.
- Zoro generation got several things right automatically:
  - strong physical description
  - useful item list
  - appropriate voice examples
  - meaningful commit points tied to major knowledge and loyalty shifts
- Famous-character identity questions may not differentiate commits well.
  - Example: asking "Who are you?" produced similar answers across Manus commits, which is acceptable for stable identity.
  - Better evaluation questions are knowledge-specific or event-specific.
- Well-known stories are a good stress test for:
  - schema quality
  - prompt quality
  - commit usefulness
  - whether the engine prompt feels believable

## Custom Story Patterns

- Red Noodle Clan material benefits from the custom story pipeline, not the famous-story path.
- Even a single dense paragraph can surface multiple characters, factions, artifacts, and relationship cues.
- Custom stories need extra scrutiny on:
  - ownership of items
  - what counts as `universe`
  - relationship precision
  - who knows what, and when
- VERA is good at finding named entities and social structure, but it may over-associate nearby artifacts or titles.
- **The 90/10 rule for original stories**
  - VERA can automate roughly 90 percent of character generation for original stories.
  - The remaining 10 percent, especially item ownership, relationship precision, and voice final tuning, always needs human eyes.
  - Never ship a custom story character without at least a quick review pass.
- For personal/original stories, human review is still essential after generation.

## Automation Opportunities

- **Auto-postprocess generated character JSON**
  - Remove duplicate voice fields automatically.
  - Validate `universe` vs `origin` semantics.

- **Auto-run a schema lint pass after every VERA generation**
  - Check for empty fields.
  - Check for suspicious origins like franchise titles.
  - Check for duplicated voice content.
  - Check for item ownership anomalies.

- **Auto-flag relational items for human review**
  - When VERA generates items for a character, any item that appears in the same passage as another named character should be automatically flagged as possibly shared or misassigned, so ownership can be verified.
  - This would catch cases like Cuatroblade being assigned to Roz instead of Manus.

- **Auto-run a quick character chat sanity test**
  - After generation, ask 1 or 2 commit-specific test questions automatically.
  - Flag responses that are too generic, too stage-direction heavy, or obviously wrong.

- **Auto-suggest voice tightening templates**
  - If responses contain quotes, self-translation, or parenthetical actions, propose a tuned voice block automatically.

- **Auto-generate a review report**
  - After VERA creates files, summarize:
    - characters found
    - commits created
    - suspicious assumptions
    - fields likely needing human correction

## Per-Character Notes

### Manus Flatfoot

- Manus works best with very hard compression rules.
- Good constraints for Manus:
  - 1 to 3 or 1 to 4 short sentences
  - no parentheticals
  - no self-translation
  - no quotation marks around replies
  - sparse, weighted language
- Example lines are very effective for Manus.
- Identity questions are not the best test for commit separation; knowledge-specific questions work much better.

### Roronoa Zoro

- VERA generated a strong first-pass famous-character profile for Zoro.
- Zoro commit suggestions were credible and usable:
  - Baratie / vow after Mihawk
  - Thriller Bark / Nothing Happened
  - Timeskip / training under Mihawk
- Main schema mistake from first pass:
  - `origin` incorrectly set to `One Piece`
- Manual correction used:
  - `universe: One Piece`
  - `origin: Shimotsuki Village, East Blue`

### Roz Kolora

- First generated version was promising, but needed corrective refinement.
- Corrections made:
  - `universe` changed from `People of Pisces` to `A Poetic Saga of the Red Noodle Clan`
  - removed incorrect `Cuatroblade` ownership
  - updated items to:
    - royal blue shark fin-shaped celluloid guitar pick on a figaro necklace
    - autogyro (green and yellow with retractable propellers)
- Voice improved significantly after replacing generic authority rules with tighter ones:
  - 1 to 3 sentences max
  - no parenthetical stage directions
  - no quotation marks
  - measured and deliberate
  - never over-explains
  - sensuous authority
- This confirms that VERA can get a strong base layer for original characters, but the last 20 percent of voice usually needs targeted tuning.

## Session 1 Victory Lap

What we proved today:

- Knowledge gating works — Manus at people_of_pisces genuinely didn't know about Planet Weapons
- VERA can extract multiple characters from a single paragraph of text automatically
- Well-known story pipeline works — Roronoa Zoro generated with zero human input
- Custom story pipeline works — entire Red Noodle Clan cast extracted from Jay's novel
- Voice rules in JSON are the right architecture — tuning a character never requires touching engine code
- Full pipeline confirmed: Browser → Next.js → SSH → Tailscale → VPS → Ollama → Character → Back to browser
- Hackermouth is alive and terrifying on mobile 👁️
- The git-as-story-timeline analogy is not just a metaphor — it's the actual architecture

What we built in one day:

- MultiVera engine with single-response and interactive modes
- VERA character prep tool with modular LLM provider support
- 7 characters from Red Noodle Clan loaded and voice-tuned
- Roronoa Zoro as proof of well-known story pipeline
- Full website integration with character chat
- Hackermouth persistent overlay with terminal chat UI
- Permanent systemd service for zero-downtime hosting
- UTF-8 encoding fixed across entire pipeline
- Next.js hydration fix documented and applied universally
