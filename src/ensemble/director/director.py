import os
import json
import time
import re
from typing import Optional, List, Dict, Any, Tuple, Union
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIStatusError

from ensemble.parser.models import SceneChunk
from ensemble.producer.models import CastSheet, CharacterProfile
from ensemble.producer.catalog import KOKORO_VOICE_CATALOG
from ensemble.director.models import ScreenplayLine, Screenplay

_project_env = Path(__file__).resolve().parents[3] / ".env"
if _project_env.exists():
    load_dotenv(dotenv_path=_project_env)
load_dotenv()


class SceneDirector:
    """
    Audio Drama Scene Director.
    Converts raw fiction prose into a multi-speaker dramatic screenplay
    with line-by-line speaker attribution, acting emotion, speed modulation,
    and pause pacing.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model = model or os.getenv("DIRECTOR_MODEL", "qwen/qwen3.8-27b")
        self.api_key = api_key or os.getenv("DIRECTOR_API_KEY", os.getenv("LLM_API_KEY", os.getenv("GROQ_API_KEY")))
        self.base_url = base_url or os.getenv("DIRECTOR_BASE_URL", os.getenv("LLM_BASE_URL", os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")))

        if not self.api_key:
            raise ValueError("DIRECTOR_API_KEY or GROQ_API_KEY is not set. Please provide it in .env or constructor.")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def _call_with_retry(self, messages: List[Dict[str, str]], max_retries: int = 3):
        """Executes LLM chat completion with backoff retry when rate limits or server spikes occur."""
        is_gpt_oss = "gpt-oss" in self.model.lower()
        backup_keys = [k for k in [os.getenv("PRODUCER_API_KEY"), os.getenv("LLM_API_KEY")] if k and k != self.api_key]
        active_client = self.client
        cur_max_tokens = None

        for attempt in range(max_retries + 1):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                }
                if cur_max_tokens is not None:
                    kwargs["max_tokens"] = cur_max_tokens
                if is_gpt_oss:
                    kwargs["extra_body"] = {"reasoning_effort": "low"}
                return active_client.chat.completions.create(**kwargs)
            except (RateLimitError, APIStatusError) as e:
                err_msg = str(e)
                status = getattr(e, "status_code", 0)
                is_rate_limit = (
                    isinstance(e, RateLimitError)
                    or "rate_limit_exceeded" in err_msg
                    or "tokens per minute" in err_msg
                    or "TPM" in err_msg
                    or "requests per" in err_msg
                    or status == 429
                )
                is_server_busy = status in (500, 502, 503, 504) or "high demand" in err_msg or "UNAVAILABLE" in err_msg

                if (is_rate_limit or is_server_busy) and attempt < max_retries:
                    # Switch to backup Groq key if available
                    if is_rate_limit and backup_keys:
                        alt_key = backup_keys.pop(0)
                        active_client = OpenAI(api_key=alt_key, base_url=self.base_url)
                        print(f"   🔄 Switched to backup LLM API key after rate limit.")
                        time.sleep(1.0)
                        continue

                    match = re.search(r"try again in ([\d\.]+)s", err_msg)
                    if match:
                        wait_sec = float(match.group(1)) + 1.5
                    elif is_server_busy:
                        wait_sec = 2.5 * (attempt + 1)
                    else:
                        wait_sec = 6.0 * (attempt + 1)

                    if "tokens per minute" in err_msg or "TPM" in err_msg or "OTPM" in err_msg or "max_tokens" in err_msg:
                        is_gemini = "gemini" in self.model.lower()
                        max_cap = 8192 if is_gemini else 1000
                        lim_match = re.search(r"Limit\s+(\d+)", err_msg, re.IGNORECASE)
                        if lim_match:
                            lim_val = int(lim_match.group(1))
                            cur_max_tokens = min(max_cap, lim_val)
                        else:
                            cur_max_tokens = max_cap
                        print(f"   ⏳ Provider enforced token limit. Clamped max_tokens to {cur_max_tokens}.")

                    if is_server_busy:
                        print(f"   ⏳ Provider experiencing temporary high demand ({status or 503}). Retrying in {wait_sec:.1f}s (attempt {attempt + 1}/{max_retries})...")
                    else:
                        print(f"   ⏳ Director rate limit reached. Waiting {wait_sec:.1f}s before retry (attempt {attempt + 1}/{max_retries})...")

                    time.sleep(wait_sec)
                    continue
                raise e

    def _split_prose_in_half(self, prose_text: str) -> Tuple[str, str]:
        """
        Splits scene prose into two balanced parts at the nearest paragraph boundary
        (or sentence boundary) closest to the 50% word count mark.
        Preserves complete paragraphs and narrative flow without cutting mid-sentence.
        """
        paras = [p.strip() for p in prose_text.split("\n\n") if p.strip()]
        if len(paras) <= 1:
            paras = [p.strip() for p in prose_text.split("\n") if p.strip()]

        if len(paras) <= 1:
            sentences = re.split(r"(?<=[.!?])\s+", prose_text)
            total_words = sum(len(s.split()) for s in sentences)
            half_words = total_words / 2
            words_so_far = 0
            split_idx = 1
            for i, s in enumerate(sentences):
                w = len(s.split())
                if words_so_far + w >= half_words:
                    split_idx = max(1, i if (half_words - words_so_far) < (words_so_far + w - half_words) else i + 1)
                    break
                words_so_far += w
            return " ".join(sentences[:split_idx]), " ".join(sentences[split_idx:])

        total_words = sum(len(p.split()) for p in paras)
        half_words = total_words / 2
        words_so_far = 0
        split_idx = 1
        for i, p in enumerate(paras):
            w = len(p.split())
            if words_so_far + w >= half_words:
                split_idx = max(1, i if (half_words - words_so_far) < (words_so_far + w - half_words) else i + 1)
                break
            words_so_far += w

        part1 = "\n\n".join(paras[:split_idx])
        part2 = "\n\n".join(paras[split_idx:])
        return part1, part2

    def _build_system_prompt(self, cast_sheet: Optional[CastSheet] = None) -> str:
        cast_list_str = ""
        if cast_sheet and cast_sheet.characters:
            lines = []
            for cid, c in cast_sheet.characters.items():
                aliases_str = ", ".join(f"'{a}'" for a in c.aliases) if c.aliases else "none"
                lines.append(f"- ID: `{cid}` | Name: {c.name} ({c.gender}, {c.role}) | Aliases: [{aliases_str}]")
            cast_list_str = "\nREGISTERED CAST MEMBERS:\n" + "\n".join(lines) + "\n"

        return f"""You are an elite Audio Drama Screenplay Director.
Your mission is to adapt raw narrative fiction prose into an expressive, line-by-line screenplay for multiple voice actors.
{cast_list_str}
RULES:
1. ACTIVE SCENE CANDIDATES & CHARACTER PRESENCE:
   - Identify which characters are physically PRESENT and active in this specific scene.
   - Output "scene_characters_present" as the FIRST field in the JSON response, listing the character IDs present (e.g. ["narrator", "char_tom"]).
   - NEVER assign dialogue to a character who is absent, elsewhere, or deceased (e.g. do NOT assign lines to a deceased character or someone who has not entered the scene).
   - If an uncast or newly introduced character speaks (e.g. newly arrived relative, telephone operator, waiter, cab driver, butler, stranger), dynamically assign them a descriptive ID (e.g. "char_gatz", "char_operator") and add them to "new_characters".

2. FIRST-PERSON POV ("I") vs THIRD-PERSON PRONOUNS ("he" / "she"):
   - When the story is told by a first-person narrator who is a character in the story (e.g. Nick Carraway, Jane Eyre, Katniss Everdeen):
     * Narration, internal thoughts, and spoken words tagged with "I said", "I asked", "I replied", or "I urged" belong to `narrator`.
     * Spoken dialogue tagged with "he said", "she said", "he replied", "she whispered", or "he muttered" belongs to the OTHER character in the scene, NEVER to `narrator`!
     * NEVER confuse third-person speech ("he said") with the first-person narrator ("I").

3. CONVERSATIONAL TURN-TAKING (DIALOGUE PING-PONG):
   - In back-and-forth dialogue exchanges between two characters, speaking turns strictly ALTERNATE:
     * Question -> Answer -> Follow-up -> Reply.
     * Consecutive alternating dialogue lines cannot be spoken by the same character unless explicitly framed as an uninterrupted monologue.
     * A character NEVER speaks both sides of an exchange or answers their own question!
     * In conversational interjections or hesitant speech where Speaker B trails off (e.g. "Mr. — —"), a short subsequent response (e.g. "Carraway.") is Speaker A identifying himself, and the continuation ("Where have they got Jimmy?") returns to Speaker B.

4. UNCAST INTERLOCUTORS & SERVICE CHARACTERS:
   - Whenever a character speaks through a telephone, orders food, asks directions, or converses with an unnamed secondary character (telephone operator, waiter, cab driver, butler, clerk, nurse, stranger), DO NOT collapse both sides onto the caller!
   - JIT-cast the interlocutor (e.g. "char_operator", "char_waiter", "char_butler") and register them in "new_characters".

5. STRICT DIALOGUE PURITY (SPOKEN WORDS ONLY):
   - Dialogue lines MUST contain spoken words only (words audibly articulated from the character's mouth, typically in quotes).
   - Strip all author tags, speech verbs, and attribution clauses (e.g. "he said", "whispered Marcus", "I asked").
   - BAD: "Put the gun down," Marcus whispered, his hands trembling.
   - GOOD: 
     - Line 1: speaker: "char_marcus", emotion: "whisper", text: "Put the gun down."
     - Line 2: speaker: "narrator", emotion: "tense", text: "His hands were trembling."

6. ACTION BEATS & PHYSICAL MOVEMENTS BELONG TO THE NARRATOR:
   - A character speaker ID can ONLY be assigned to words spoken aloud in conversation.
   - Any physical action, movement, gesture, entrance/exit, or description of a character (even if their name is the subject of the sentence!) is DESCRIPTIVE NARRATION and MUST be assigned to "narrator".
   - A character voice actor must NEVER utter third-person sentences describing themselves or others!
   - BAD: speaker: "char_daisy", text: "Then suddenly she threw her napkin on the table and excused herself." (WRONG: This is an action beat describing Daisy, not her speaking!)
   - GOOD: speaker: "narrator", text: "Then suddenly she threw her napkin on the table and excused herself and went into the house."
   - BAD: speaker: "char_tom", text: "Tom and Miss Baker with several feet of twilight between them strolled back into the library." (WRONG: Third-person action, must be narrator!)
   - GOOD: speaker: "narrator", text: "Tom and Miss Baker with several feet of twilight between them strolled back into the library."

7. ACTING DIRECTION:
   - emotion: 1 expressive acting instruction word (e.g. "tense", "whisper", "sarcastic", "arrogant", "warm", "mournful", "urgent", "flirtatious", "calm", "bored", "furious").
   - speed: float between 0.90 and 1.10 (0.95 for slow/deliberate/solemn; 1.0 for normal; 1.05 for hurried/agitated).
   - pause_after_ms: integer milliseconds of silence to follow the line (350-450ms for dialogue exchanges; 550-700ms after narrative descriptions or scene beats).

8. DISTINCT QUOTES MUST BE SEPARATE SCREENPLAY LINES:
   - If a passage of text contains multiple distinct dialogue quotes (even if they appear next to each other in the same paragraph, e.g. "'Do they miss me?' she cried ecstatically. 'The whole town is desolate...'"), NEVER merge them into a single screenplay line or speaker!
   - Split each quote into its own separate line and attribute each to its proper speaker.
   - Dialogue quotes that represent an exchange or reply (e.g. Daisy asks "Do they miss me?" -> Nick replies "The whole town is desolate...") MUST be split and assigned to their respective speakers according to conversational turn-taking.

9. STRICT FULL-TEXT AUDIO DRAMA FIDELITY (NO SKIPPING OR CONDENSING):
   - This is an UNABRIDGED audio drama performance. You MUST preserve and adapt the FULL story without skipping or condensing.
   - ALL sentences and paragraphs from the source text must be converted sequentially into screenplay lines:
     * Spoken dialogue (words audibly spoken aloud in conversation) -> assigned to the respective character ID.
     * Narration, internal thoughts, background exposition, descriptions of places, and character reflections -> assigned to "narrator".
   - NEVER summarize, skip, condense, or omit ANY paragraphs.
   - A 1,000-word scene must produce a complete screenplay representing the entire text from the very first sentence to the very last sentence. Every paragraph must be heard by the listener.

10. RESPONSE FORMAT:
   Return ONLY a valid JSON object matching this schema:
{{
  "scene_characters_present": ["narrator", "char_tom"],
  "lines": [
    {{
      "speaker": "narrator",
      "emotion": "measured",
      "text": "The wind died down toward midnight, leaving the bay still as glass.",
      "speed": 1.0,
      "pause_after_ms": 550
    }},
    {{
      "speaker": "char_tom",
      "emotion": "arrogant",
      "text": "We ought to go into town and have a drink.",
      "speed": 1.02,
      "pause_after_ms": 400
    }}
  ],
  "new_characters": []
}}"""

    def _pick_unused_voice(self, gender: str, used_voices: set, default_narrator: str = "bm_george") -> str:
        gender_norm = gender.lower()
        for vid, v in KOKORO_VOICE_CATALOG.items():
            if v.gender == gender_norm and vid not in used_voices and vid != default_narrator:
                return vid
        for vid in KOKORO_VOICE_CATALOG.keys():
            if vid not in used_voices and vid != default_narrator:
                return vid
        return "am_adam" if gender_norm == "male" else "af_sarah"

    def direct_scene(
        self,
        scene: SceneChunk | str,
        cast_sheet: Optional[CastSheet] = None,
        chapter_index: int = 1,
        scene_index: int = 1,
        previous_scene_context: Optional[str] = None,
        _allow_split: bool = True,
    ) -> tuple[Screenplay, Optional[CastSheet]]:
        """
        Directs a raw scene chunk into a performance screenplay.
        If new characters are encountered, dynamically registers them in the cast_sheet.
        Returns:
            (Screenplay, updated_cast_sheet)
        """
        if isinstance(scene, SceneChunk):
            prose_text = scene.text
            ch_idx = scene.chapter_index
            s_idx = scene.scene_index
        else:
            prose_text = str(scene)
            ch_idx = chapter_index
            s_idx = scene_index

        system_prompt = self._build_system_prompt(cast_sheet)
        user_prompt = ""
        if previous_scene_context and previous_scene_context.strip():
            user_prompt += (
                "[PREVIOUS SCENE CONTEXT (For character continuity and pronoun resolution only - DO NOT re-direct these lines)]:\n"
                f"{previous_scene_context.strip()}\n\n"
            )
        user_prompt += f"Convert this ENTIRE scene into an unabridged audio drama screenplay without skipping or summarizing ANY text:\n\n\"\"\"\n{prose_text.strip()}\n\"\"\""

        response = self._call_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        choice = response.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        raw_content = choice.message.content or "{}"
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            # Fallback: extract JSON block if wrapped in markdown
            match = re.search(r"\{.*\}", raw_content, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except Exception:
                    parsed = {}
            else:
                parsed = {}

        raw_lines = parsed.get("lines", [])
        if not raw_lines and isinstance(parsed, list):
            raw_lines = parsed

        # Dynamic 2-Way Scene Split Fallback:
        # If the scene hit output token limits (finish_reason == "length") or truncated JSON (0 lines parsed
        # for a substantial scene > 250 words), split the scene into 2 balanced parts and direct each part.
        scene_word_count = len(prose_text.split())
        if _allow_split and scene_word_count > 250 and (finish_reason == "length" or not raw_lines):
            print(f"   ✂️ Scene {s_idx} hit token limit ({scene_word_count} words, finish_reason={finish_reason}). Dynamically splitting into 2 parts to preserve full context...")
            part1_text, part2_text = self._split_prose_in_half(prose_text)

            # Direct Part 1
            sp1, cast_sheet = self.direct_scene(
                scene=part1_text,
                cast_sheet=cast_sheet,
                chapter_index=ch_idx,
                scene_index=s_idx,
                previous_scene_context=previous_scene_context,
                _allow_split=False,
            )

            # Gentle pacing interval between split parts for provider rate limits
            time.sleep(1.0)

            # Prepare context handoff for Part 2 from the conclusion of Part 1
            if sp1.lines:
                handoff_lines = "\n".join([f"{l.speaker}: {l.text}" for l in sp1.lines[-3:]])
                part2_context = f"[PREVIOUS SCENE CONTEXT (Part 1 of this scene just concluded with)]:\n{handoff_lines}"
            else:
                part2_context = previous_scene_context

            # Direct Part 2
            sp2, cast_sheet = self.direct_scene(
                scene=part2_text,
                cast_sheet=cast_sheet,
                chapter_index=ch_idx,
                scene_index=s_idx,
                previous_scene_context=part2_context,
                _allow_split=False,
            )

            # Combine lines and unique characters present
            combined_lines = sp1.lines + sp2.lines
            combined_chars = list(dict.fromkeys(sp1.scene_characters_present + sp2.scene_characters_present))

            combined_screenplay = Screenplay(
                chapter_index=ch_idx,
                scene_index=s_idx,
                lines=combined_lines,
                scene_characters_present=combined_chars,
            )
            print(f"   ✨ Dynamic split resolved Scene {s_idx}: {len(sp1.lines)} + {len(sp2.lines)} = {len(combined_lines)} lines with full character attribution.")
            return combined_screenplay, cast_sheet

        # Dynamic Character Registration (JIT Casting)
        new_chars = parsed.get("new_characters", [])
        if new_chars and cast_sheet and isinstance(new_chars, list):
            used_voices = {c.voice_id for c in cast_sheet.characters.values()}
            for nc in new_chars:
                if isinstance(nc, dict):
                    name = nc.get("name", "").strip() or nc.get("id", "").strip()
                    gender = str(nc.get("gender", "male")).lower()
                    age_group = str(nc.get("age_group", "adult"))
                    role = str(nc.get("role", "supporting"))
                    traits = nc.get("personality_traits", [])
                    personality_traits = traits if isinstance(traits, list) else [str(traits)]
                elif isinstance(nc, str):
                    name = nc.strip()
                    gender = "male"
                    age_group = "adult"
                    role = "supporting"
                    personality_traits = []
                else:
                    continue

                if not name:
                    continue

                # Strip char_ prefix if present to derive clean human-readable name
                clean_name = name
                if clean_name.lower().startswith("char_"):
                    clean_name = clean_name[5:].replace("_", " ").title()

                char_slug = name.lower() if name.lower().startswith("char_") else f"char_{name.lower().replace(' ', '_')}"
                if char_slug in cast_sheet.characters:
                    continue

                # Check if this character already matches an existing character or narrator by name/alias
                existing_char = (
                    cast_sheet.get_character_for_speaker(name)
                    or cast_sheet.get_character_for_speaker(char_slug)
                    or cast_sheet.get_character_for_speaker(clean_name)
                )
                if existing_char:
                    # Link alias so char_slug resolves to the existing character
                    if char_slug not in cast_sheet.characters:
                        cast_sheet.characters[char_slug] = existing_char
                    continue

                voice_id = self._pick_unused_voice(gender, used_voices, cast_sheet.default_narrator_voice)
                used_voices.add(voice_id)

                profile = CharacterProfile(
                    id=char_slug,
                    name=clean_name,
                    gender=gender,
                    age_group=age_group,
                    role=role,
                    personality_traits=personality_traits,
                    aliases=[clean_name, name],
                    voice_id=voice_id,
                    voice_rationale=f"Dynamically cast during Scene {s_idx} direction."
                )
                cast_sheet.characters[char_slug] = profile
                print(f"   🎭 JIT Casting: Discovered '{clean_name}' ({char_slug}) in Scene {s_idx} -> Assigned voice '{voice_id}'")

        # Map and sanitize lines
        screenplay_lines: List[ScreenplayLine] = []
        for d in raw_lines:
            if not isinstance(d, dict):
                continue
            text = d.get("text", "").strip()
            if not text:
                continue

            raw_speaker = d.get("speaker", "narrator").strip().lower()
            
            # Resolve speaker to known character ID or alias if necessary
            resolved_speaker = raw_speaker
            if cast_sheet and raw_speaker != "narrator":
                # First check alias / name resolution
                char_match = cast_sheet.get_character_for_speaker(raw_speaker)
                if char_match:
                    resolved_speaker = char_match.id
                elif raw_speaker in cast_sheet.characters:
                    resolved_speaker = cast_sheet.characters[raw_speaker].id

            raw_speed = d.get("speed", 1.0)
            if isinstance(raw_speed, str):
                speed_map = {"slow": 0.95, "normal": 1.0, "fast": 1.05, "very slow": 0.90, "very fast": 1.10}
                speed = speed_map.get(raw_speed.lower().strip(), 1.0)
            else:
                try:
                    speed = float(raw_speed)
                except (ValueError, TypeError):
                    speed = 1.0
            # Clamp speed to sane acoustic range for Kokoro (0.85 - 1.15)
            speed = max(0.85, min(1.15, speed))

            try:
                pause_after_ms = int(d.get("pause_after_ms", 400 if resolved_speaker != "narrator" else 550))
            except (ValueError, TypeError):
                pause_after_ms = 400 if resolved_speaker != "narrator" else 550

            screenplay_lines.append(
                ScreenplayLine(
                    speaker=resolved_speaker,
                    text=text,
                    emotion=d.get("emotion", "neutral"),
                    speed=speed,
                    pause_after_ms=pause_after_ms,
                )
            )

        # Defensive Auto-Cast Safeguard: ensure every spoken character is registered with a distinct voice
        if cast_sheet:
            used_voices = {c.voice_id for c in cast_sheet.characters.values()}
            for spl in screenplay_lines:
                spk = spl.speaker
                if spk != "narrator" and spk not in cast_sheet.characters:
                    # Check if it matches an existing character or narrator by alias/name
                    char_match = cast_sheet.get_character_for_speaker(spk)
                    if char_match:
                        spl.speaker = char_match.id
                        continue

                    clean_name = spk.replace("char_", "").replace("_", " ").title()

                    fem_hints = ["miss", "mrs", "ms", "lady", "girl", "woman", "daisy", "jordan", "baker", "catherine", "myrtle", "madam"]
                    male_hints = ["mr", "lord", "sir", "boy", "man", "tom", "nick", "gatsby", "father", "son", "brother", "waiter", "butler"]
                    is_female = any(h in spk.lower() for h in fem_hints)
                    is_male = any(h in spk.lower() for h in male_hints)
                    if not is_female and not is_male and isinstance(prose_text, str):
                        clean_lower = clean_name.lower()
                        he_count = len(re.findall(rf"\b(he|him|his)\b", prose_text, re.IGNORECASE))
                        she_count = len(re.findall(rf"\b(she|her)\b", prose_text, re.IGNORECASE))
                        if she_count > he_count:
                            is_female = True

                    gender = "female" if is_female else "male"
                    voice_id = self._pick_unused_voice(gender, used_voices, cast_sheet.default_narrator_voice)
                    used_voices.add(voice_id)

                    profile = CharacterProfile(
                        id=spk,
                        name=clean_name,
                        gender=gender,
                        age_group="adult",
                        role="supporting",
                        personality_traits=["discovered_speaker"],
                        aliases=[clean_name],
                        voice_id=voice_id,
                        voice_rationale=f"Defensively auto-cast during Scene {s_idx} direction."
                    )
                    cast_sheet.characters[spk] = profile
                    print(f"   🎭 Auto-Cast Safeguard: Discovered unregistered speaker '{clean_name}' ({gender}) in Scene {s_idx} -> Assigned voice '{voice_id}'")

        # Fallback safeguard: if LLM failed to return lines but prose_text exists,
        # ensure story prose is never dropped or skipped by creating a narrator line.
        if not screenplay_lines and prose_text.strip():
            print(f"   ⚠️ Scene {s_idx} direction produced 0 lines. Falling back to default narrator prose.")
            screenplay_lines.append(
                ScreenplayLine(
                    speaker="narrator",
                    text=prose_text.strip(),
                    emotion="neutral",
                    speed=1.0,
                    pause_after_ms=500,
                )
            )

        raw_scene_chars = parsed.get("scene_characters_present", [])
        if not isinstance(raw_scene_chars, list):
            raw_scene_chars = []

        screenplay = Screenplay(
            chapter_index=ch_idx,
            scene_index=s_idx,
            lines=screenplay_lines,
            scene_characters_present=[str(c) for c in raw_scene_chars],
        )

        return screenplay, cast_sheet
