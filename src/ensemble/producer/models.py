import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class CharacterProfile:
    """
    Profile for a character in the fiction novel, containing persona traits,
    alias variants for speaker resolution, and assigned Kokoro voice.
    """
    id: str                         # Unique key e.g. "char_gatsby", "char_nick", "narrator"
    name: str                       # Full display name e.g. "Jay Gatsby"
    gender: str                     # "male" | "female" | "unknown"
    age_group: str                  # "young" | "adult" | "elderly"
    role: str                       # "narrator" | "protagonist" | "antagonist" | "supporting" | "minor"
    personality_traits: List[str]   # e.g. ["mysterious", "wealthy", "melancholy"]
    aliases: List[str]              # e.g. ["Gatsby", "Mr. Gatsby", "Jay", "the host"]
    voice_id: str                   # e.g. "am_michael"
    voice_rationale: str = ""       # Why the producer selected this voice


@dataclass
class CastSheet:
    """
    Master cast sheet for an entire fiction book, persisting character-to-voice
    mappings and alias resolution for the Scene Director.
    """
    book_title: str
    characters: Dict[str, CharacterProfile] = field(default_factory=dict)
    narrator_id: str = "narrator"

    def get_narrator(self) -> Optional[CharacterProfile]:
        return self.characters.get(self.narrator_id)

    def get_character_for_speaker(self, speaker_name: str) -> Optional[CharacterProfile]:
        """
        Resolves a raw speaker tag from the Scene Director (e.g. 'mr. gatsby', 'gatsby', 'tom')
        to its canonical CharacterProfile using ID, name, and alias matching.
        """
        norm = speaker_name.strip().lower()

        # 1. Direct match on ID
        if norm in self.characters:
            return self.characters[norm]

        # 2. Match on primary character name
        for char in self.characters.values():
            if char.name.lower() == norm:
                return char

        # 3. Match against known aliases
        for char in self.characters.values():
            for alias in char.aliases:
                if alias.lower() == norm:
                    return char

        # 4. Partial / fuzzy match on aliases or names
        for char in self.characters.values():
            if norm in char.name.lower() or char.name.lower() in norm:
                return char
            for alias in char.aliases:
                if norm in alias.lower() or alias.lower() in norm:
                    return char

        return None

    def get_voice_for_speaker(self, speaker_name: str) -> str:
        """
        Resolves a speaker name to their Kokoro voice_id.
        Falls back to the narrator voice if unknown.
        """
        char = self.get_character_for_speaker(speaker_name)
        if char and char.voice_id:
            return char.voice_id

        narrator = self.get_narrator()
        return narrator.voice_id if narrator else "bm_george"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CastSheet":
        chars = {}
        for k, v in data.get("characters", {}).items():
            chars[k] = CharacterProfile(**v)
        return cls(
            book_title=data.get("book_title", "Untitled"),
            characters=chars,
            narrator_id=data.get("narrator_id", "narrator")
        )

    def save_json(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_json(cls, path: str | Path) -> "CastSheet":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Cast sheet not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
