from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import json


@dataclass
class ScreenplayLine:
    """
    A single performance line in an audio drama screenplay.
    """
    speaker: str              # Character ID (e.g. "narrator", "char_tom", "char_daisy")
    text: str                 # Clean spoken prose or dialogue (author tags removed)
    emotion: str = "neutral"  # Performance delivery mood (e.g. "tense", "wistful", "arrogant", "whisper")
    speed: float = 1.0        # Speech rate multiplier (0.9 to 1.1)
    pause_after_ms: int = 400 # Silence duration in milliseconds to append after this line

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScreenplayLine":
        return cls(
            speaker=data.get("speaker", "narrator"),
            text=data.get("text", "").strip(),
            emotion=data.get("emotion", "neutral"),
            speed=float(data.get("speed", 1.0)),
            pause_after_ms=int(data.get("pause_after_ms", 400)),
        )


@dataclass
class Screenplay:
    """
    A complete performance screenplay for a single scene chunk.
    """
    chapter_index: int
    scene_index: int
    lines: List[ScreenplayLine] = field(default_factory=list)

    @property
    def total_words(self) -> int:
        return sum(len(line.text.split()) for line in self.lines)

    @property
    def speaker_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for line in self.lines:
            counts[line.speaker] = counts.get(line.speaker, 0) + 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_index": self.chapter_index,
            "scene_index": self.scene_index,
            "total_words": self.total_words,
            "lines": [line.to_dict() for line in self.lines],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Screenplay":
        lines = [ScreenplayLine.from_dict(d) for d in data.get("lines", [])]
        return cls(
            chapter_index=int(data.get("chapter_index", 1)),
            scene_index=int(data.get("scene_index", 1)),
            lines=lines,
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "Screenplay":
        return cls.from_dict(json.loads(json_str))
