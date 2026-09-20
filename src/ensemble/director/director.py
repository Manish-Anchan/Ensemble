import os
import json
import time
import re
from typing import Optional, List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIStatusError

from ensemble.parser.models import SceneChunk
from ensemble.producer.models import CastSheet, CharacterProfile
from ensemble.producer.catalog import KOKORO_VOICE_CATALOG
from ensemble.director.models import ScreenplayLine, Screenplay

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
                        print(f"   ⏳ Provider experiencing temporary high demand ({status or 503}). Retrying in {wait_sec:.1f}s...")
                    else:
                        match = re.search(r"try again in ([\d\.]+)s", err_msg)
                        wait_sec = float(match.group(1)) + 1.5 if match else (12.0 * (attempt + 1))
                        print(f"   ⏳ Director rate limit reached. Waiting {wait_sec:.1f}s before retry...")
                    time.sleep(wait_sec)
                    continue
                raise e

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
1. IDENTIFY ALL LINES:
   - Split the scene prose into sequential units: dialogue lines and narrative descriptive blocks.
   - For narrative blocks, set speaker to "narrator".
   - For spoken dialogue, set speaker to the exact character ID from the cast list above (e.g. "char_tom", "char_daisy", "char_jordan").

2. STRICT DIALOGUE PURITY (STRIP AUTHOR TAGS):
   - Dialogue lines MUST contain spoken words only. Strip all author tags, speech verbs, and attribution clauses.
   - BAD: "Put the gun down," Marcus whispered, his hands trembling.
   - GOOD: 
     - Line 1: speaker: "char_marcus", emotion: "whisper", text: "Put the gun down."
     - Line 2: speaker: "narrator", emotion: "tense", text: "His hands were trembling."

3. ACTING DIRECTION:
   - emotion: 1 expressive acting instruction word (e.g. "tense", "whisper", "sarcastic", "arrogant", "warm", "mournful", "urgent", "flirtatious", "calm", "bored", "furious").
   - speed: float between 0.90 and 1.10 (0.95 for slow/deliberate/solemn; 1.0 for normal; 1.05 for hurried/agitated).
   - pause_after_ms: integer milliseconds of silence to follow the line (350-450ms for dialogue exchanges; 550-700ms after narrative descriptions or scene beats).

4. DYNAMIC UNREGISTERED CHARACTERS:
   - If a character speaks who is NOT in the registered cast, use a slug like "char_catherine" as speaker, and list them in the "new_characters" array with their name, gender ("male"|"female"), and personality_traits.

5. RESPONSE FORMAT:
   Return ONLY a valid JSON object matching this schema:
{{
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
        user_prompt = f"Convert this scene into a dramatic screenplay JSON:\n\n\"\"\"\n{prose_text.strip()}\n\"\"\""

        response = self._call_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        raw_content = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            # Fallback: extract JSON block if wrapped in markdown
            match = re.search(r"\{.*\}", raw_content, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else {}

        raw_lines = parsed.get("lines", [])
        if not raw_lines and isinstance(parsed, list):
            raw_lines = parsed

        # Dynamic Character Registration (JIT Casting)
        new_chars = parsed.get("new_characters", [])
        if new_chars and cast_sheet:
            used_voices = {c.voice_id for c in cast_sheet.characters.values()}
            for nc in new_chars:
                name = nc.get("name", "").strip()
                if not name:
                    continue
                char_slug = f"char_{name.lower().replace(' ', '_')}"
                if char_slug in cast_sheet.characters:
                    continue
                
                gender = nc.get("gender", "male").lower()
                voice_id = self._pick_unused_voice(gender, used_voices, cast_sheet.default_narrator_voice)
                used_voices.add(voice_id)

                profile = CharacterProfile(
                    id=char_slug,
                    name=name,
                    gender=gender,
                    age_group=nc.get("age_group", "adult"),
                    role=nc.get("role", "supporting"),
                    personality_traits=nc.get("personality_traits", []),
                    aliases=[name],
                    voice_id=voice_id,
                    voice_rationale=f"Dynamically cast during Scene {s_idx} direction."
                )
                cast_sheet.characters[char_slug] = profile
                print(f"   🎭 JIT Casting: Discovered '{name}' in Scene {s_idx} -> Assigned voice '{voice_id}'")

        # Map and sanitize lines
        screenplay_lines: List[ScreenplayLine] = []
        for d in raw_lines:
            text = d.get("text", "").strip()
            if not text:
                continue

            raw_speaker = d.get("speaker", "narrator").strip().lower()
            
            # Resolve speaker to known character ID or alias if necessary
            resolved_speaker = raw_speaker
            if cast_sheet and raw_speaker != "narrator":
                # Check if it directly matches an ID
                if raw_speaker not in cast_sheet.characters:
                    # Try finding by name or alias
                    for cid, c in cast_sheet.characters.items():
                        if raw_speaker == c.name.lower() or raw_speaker in [a.lower() for a in c.aliases]:
                            resolved_speaker = cid
                            break
                        if raw_speaker.replace("char_", "") in c.name.lower():
                            resolved_speaker = cid
                            break

            speed = float(d.get("speed", 1.0))
            # Clamp speed to sane acoustic range for Kokoro (0.85 - 1.15)
            speed = max(0.85, min(1.15, speed))

            pause_after_ms = int(d.get("pause_after_ms", 400 if resolved_speaker != "narrator" else 550))

            screenplay_lines.append(
                ScreenplayLine(
                    speaker=resolved_speaker,
                    text=text,
                    emotion=d.get("emotion", "neutral"),
                    speed=speed,
                    pause_after_ms=pause_after_ms,
                )
            )

        screenplay = Screenplay(
            chapter_index=ch_idx,
            scene_index=s_idx,
            lines=screenplay_lines,
        )

        return screenplay, cast_sheet
