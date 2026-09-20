import os
import json
import time
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from dotenv import load_dotenv
import re
from openai import OpenAI, RateLimitError, APIStatusError

from ensemble.producer.models import CharacterProfile, CastSheet
from ensemble.producer.catalog import (
    KOKORO_VOICE_CATALOG,
    get_default_narrator_voice,
    format_catalog_for_prompt,
)

load_dotenv()


class CastingProducer:
    """
    Executive AI Casting Producer.
    Analyzes novel prose chapter-by-chapter to extract characters, determine demographic
    and personality traits, resolve aliases, and cast distinct Kokoro voices with zero collisions.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        narrator_voice: Optional[str] = None,
    ):
        self.model = model or os.getenv("PRODUCER_MODEL", "qwen/qwen3.8-27b")
        self.api_key = api_key or os.getenv("PRODUCER_API_KEY", os.getenv("LLM_API_KEY", os.getenv("GROQ_API_KEY")))
        self.base_url = base_url or os.getenv("PRODUCER_BASE_URL", os.getenv("LLM_BASE_URL", os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")))
        self.default_narrator_voice = narrator_voice or "bm_george"

        if not self.api_key:
            raise ValueError("PRODUCER_API_KEY or GROQ_API_KEY is not set. Please provide it in .env or pass to CastingProducer.")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def _call_with_retry(self, messages: List[Dict[str, str]], max_retries: int = 3):
        """Executes LLM chat completion with backoff retry when rate limits or transient server spikes occur."""
        for attempt in range(max_retries + 1):
            try:
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.2,
                    response_format={"type": "json_object"}
                )
            except (RateLimitError, APIStatusError) as e:
                err_msg = str(e)
                status = getattr(e, "status_code", 0)
                is_rate_limit = (
                    isinstance(e, RateLimitError)
                    or "rate_limit_exceeded" in err_msg
                    or "tokens per minute" in err_msg
                    or "TPM" in err_msg
                    or status == 429
                )
                is_server_busy = status in (500, 502, 503, 504) or "high demand" in err_msg or "UNAVAILABLE" in err_msg

                if (is_rate_limit or is_server_busy) and attempt < max_retries:
                    if is_server_busy:
                        wait_sec = 2.5 * (attempt + 1)
                        print(f"   ⏳ Provider experiencing temporary high demand ({status or 503}). Retrying in {wait_sec:.1f}s (attempt {attempt + 1}/{max_retries})...")
                    else:
                        match = re.search(r"try again in ([\d\.]+)s", err_msg)
                        wait_sec = float(match.group(1)) + 1.5 if match else (10.0 * (attempt + 1))
                        print(f"   ⏳ Rate limit reached. Waiting {wait_sec:.1f}s before retry (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait_sec)
                    continue
                raise e

    def _pick_unused_voice(self, gender: str, used_voices: set) -> str:
        """Finds an unused Kokoro voice matching the target gender to avoid collisions."""
        gender_norm = gender.lower()
        # 1. Match requested gender among unused voices
        for vid, v in KOKORO_VOICE_CATALOG.items():
            if v.gender == gender_norm and vid not in used_voices and vid != self.default_narrator_voice:
                return vid
        # 2. Fallback: Any unused voice
        for vid in KOKORO_VOICE_CATALOG.keys():
            if vid not in used_voices and vid != self.default_narrator_voice:
                return vid
        # 3. Ultimate fallback if all 28 voices exhausted
        return "am_adam" if gender_norm == "male" else "af_sarah"

    def _build_system_prompt(self) -> str:
        catalog_str = format_catalog_for_prompt()
        return f"""You are the Executive Casting Producer for a prestigious multi-cast audio drama studio.
Your mission is to read narrative fiction prose and cast voice actors for every character.

AVAILABLE VOICE CATALOG:
{catalog_str}

RULES:
1. IDENTIFY THE NARRATOR:
   - Determine if the narrator is First-Person (e.g. Nick Carraway in Gatsby, who is both narrator and character) or Third-Person Omniscient.
   - If First-Person, note their character name in the narrator profile.
   - The Narrator must have ID "narrator".

2. IDENTIFY ALL SPEAKING & PROMINENT CHARACTERS:
   - For every character who speaks or takes action in the scene:
     - id: lowercase slug like "char_gatsby", "char_daisy", "char_tom", "char_jordan".
     - name: Full canonical name (e.g. "Jay Gatsby", "Daisy Buchanan").
     - gender: "male" or "female".
     - age_group: "young", "adult", or "elderly".
     - role: "narrator", "protagonist", "antagonist", "supporting", or "minor".
     - personality_traits: List of 2-4 descriptive adjectives.
     - aliases: List of all names/nicknames/titles used to refer to this character in dialogue or narrative (e.g. ["Gatsby", "Mr. Gatsby", "Jay"]).
     - voice_id: Exactly one voice_id chosen from the AVAILABLE VOICE CATALOG above. Match the character's gender, age, and personality.
     - voice_rationale: 1 concise sentence explaining why this voice suits the character.

3. VOICE COLLISION PREVENTION:
   - Distinct primary/secondary characters MUST have different voice_ids! Do not cast the same voice for two different main characters.

4. RESPONSE FORMAT:
   Return ONLY a valid JSON object matching this exact schema:
{{
  "book_title": "string",
  "narrator_type": "first_person" or "third_person",
  "characters": [
    {{
      "id": "narrator",
      "name": "Story Narrator (or Character Name)",
      "gender": "male" or "female",
      "age_group": "adult",
      "role": "narrator",
      "personality_traits": ["observant", "measured"],
      "aliases": ["narrator"],
      "voice_id": "bm_george",
      "voice_rationale": "Warm British storyteller fits the classic narrative prose."
    }},
    {{
      "id": "char_tom",
      "name": "Tom Buchanan",
      "gender": "male",
      "age_group": "adult",
      "role": "antagonist",
      "personality_traits": ["arrogant", "hulking", "aggressive"],
      "aliases": ["Tom", "Buchanan", "Mr. Buchanan"],
      "voice_id": "am_adam",
      "voice_rationale": "Deep, gruff American baritone fits a brutish, imposing ex-athlete."
    }}
  ]
}}"""

    def cast_characters(
        self,
        book_title: str,
        prose_sample: str,
        existing_cast_sheet: Optional[CastSheet] = None
    ) -> CastSheet:
        """
        Runs the Casting Producer LLM on novel text to discover characters and assign voices.
        If existing_cast_sheet is provided, preserves previously cast characters and only casts new ones.
        """
        system_prompt = self._build_system_prompt()
        user_prompt = f"Book Title: {book_title}\n\nSCENE PROSE FOR CASTING:\n\"\"\"\n{prose_sample.strip()}\n\"\"\"\n\n"

        if existing_cast_sheet and existing_cast_sheet.characters:
            existing_lines = []
            for c in existing_cast_sheet.characters.values():
                existing_lines.append(f"- {c.name} (id: '{c.id}', voice: '{c.voice_id}', aliases: {c.aliases})")
            user_prompt += (
                "ALREADY CAST CHARACTERS:\n"
                + "\n".join(existing_lines)
                + "\n\nINSTRUCTIONS FOR THIS SCENE:\n"
                "1. Discover any NEW speaking or prominent characters introduced in this scene.\n"
                "2. For every NEW character, assign a voice from the AVAILABLE VOICE CATALOG that is NOT already used.\n"
                "3. If an already-cast character appears, you can update their aliases or traits, but DO NOT reassign their voice.\n"
                "4. If no new characters appear in this scene, preserve existing characters.\n"
                "5. Return the complete list of characters (existing + newly discovered) in valid JSON."
            )
        else:
            user_prompt += "Please analyze all characters in this opening scene and generate the master Cast Sheet JSON."

        response = self._call_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        raw_content = response.choices[0].message.content or "{}"
        parsed = json.loads(raw_content)

        # Build / merge CastSheet
        characters_dict: Dict[str, CharacterProfile] = {}
        used_voices = set()

        if existing_cast_sheet:
            for cid, c in existing_cast_sheet.characters.items():
                characters_dict[cid] = c
                used_voices.add(c.voice_id)

        chars_list = parsed.get("characters", [])
        for c in chars_list:
            char_id = c.get("id", "").strip().lower()
            name = c.get("name", "").strip()
            if not char_id or not name:
                continue

            # Check if this character matches an already existing profile
            matched_id = None
            if char_id in characters_dict:
                matched_id = char_id
            else:
                for ex_id, ex in characters_dict.items():
                    if name.lower() == ex.name.lower() or name.lower() in [a.lower() for a in ex.aliases]:
                        matched_id = ex_id
                        break

            if matched_id:
                # Merge into existing character profile: preserve voice, combine aliases & traits
                ex = characters_dict[matched_id]
                merged_aliases = sorted(list(set(ex.aliases + c.get("aliases", []))))
                merged_traits = sorted(list(set(ex.personality_traits + c.get("personality_traits", []))))
                characters_dict[matched_id] = CharacterProfile(
                    id=ex.id,
                    name=ex.name,
                    gender=ex.gender,
                    age_group=ex.age_group,
                    role=ex.role if ex.role in ("narrator", "protagonist") else c.get("role", ex.role),
                    personality_traits=merged_traits,
                    aliases=merged_aliases,
                    voice_id=ex.voice_id,  # Voice assignment never changes!
                    voice_rationale=ex.voice_rationale or c.get("voice_rationale", "")
                )
            else:
                # Brand new character
                voice_id = c.get("voice_id", "")
                gender = c.get("gender", "male").lower()

                # Validate or resolve collision
                if not voice_id or voice_id not in KOKORO_VOICE_CATALOG or voice_id in used_voices:
                    voice_id = self._pick_unused_voice(gender, used_voices)

                used_voices.add(voice_id)

                profile = CharacterProfile(
                    id=char_id,
                    name=name,
                    gender=c.get("gender", "unknown"),
                    age_group=c.get("age_group", "adult"),
                    role=c.get("role", "supporting"),
                    personality_traits=c.get("personality_traits", []),
                    aliases=c.get("aliases", []),
                    voice_id=voice_id,
                    voice_rationale=c.get("voice_rationale", "")
                )
                characters_dict[char_id] = profile

        # Ensure narrator is present
        if "narrator" not in characters_dict:
            characters_dict["narrator"] = CharacterProfile(
                id="narrator",
                name="Narrator",
                gender="male",
                age_group="adult",
                role="narrator",
                personality_traits=["observant", "storyteller"],
                aliases=["narrator"],
                voice_id=self.default_narrator_voice,
                voice_rationale="Default classic British fiction narrator."
            )

        cast_sheet = CastSheet(
            book_title=book_title,
            characters=characters_dict,
            narrator_id="narrator"
        )

        return cast_sheet

    def cast_scene(
        self,
        book_title: str,
        scene_text: str,
        scene_index: int = 1,
        total_scenes: Optional[int] = None,
        existing_cast_sheet: Optional[CastSheet] = None,
    ) -> tuple[CastSheet, List[CharacterProfile]]:
        """
        Casts characters from a single scene chunk (~400-800 words).
        Returns:
            (updated_cast_sheet, list_of_newly_discovered_characters)
        """
        prev_ids = set(existing_cast_sheet.characters.keys()) if existing_cast_sheet else set()
        updated_sheet = self.cast_characters(book_title, scene_text, existing_cast_sheet=existing_cast_sheet)
        new_profiles = [
            char for cid, char in updated_sheet.characters.items()
            if cid not in prev_ids and cid != "narrator"
        ]
        return updated_sheet, new_profiles

    def cast_chapter_scenes(
        self,
        book_title: str,
        scenes: List[Any],
        existing_cast_sheet: Optional[CastSheet] = None,
        on_scene_done: Optional[Any] = None,
    ) -> CastSheet:
        """
        Sequentially iterates through scene chunks (~600 words each), casting characters
        in an incremental assembly-line stream.
        """
        sheet = existing_cast_sheet
        for s in scenes:
            t0 = time.time()
            text = getattr(s, "text", str(s))
            s_idx = getattr(s, "scene_index", 1)
            sheet, new_chars = self.cast_scene(
                book_title=book_title,
                scene_text=text,
                scene_index=s_idx,
                total_scenes=len(scenes),
                existing_cast_sheet=sheet,
            )
            duration = time.time() - t0
            if on_scene_done:
                on_scene_done(s, sheet, new_chars, duration)
        return sheet
