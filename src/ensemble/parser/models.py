from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path


@dataclass
class SceneChunk:
    """
    A self-contained scene slice (~400-800 words) ready for the Scene Director LLM.
    """
    chapter_index: int
    scene_index: int
    text: str
    word_count: int
    start_paragraph: int
    end_paragraph: int


@dataclass
class Chapter:
    """
    A full story chapter with clean text and segmented scene chunks.
    """
    index: int
    title: str
    raw_text: str
    clean_text: str
    page_start: int
    page_end: int
    scenes: List[SceneChunk] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.clean_text.split())


@dataclass
class Book:
    """
    The parsed book representation.
    """
    title: str
    author: Optional[str] = None
    format: str = "pdf"  # "pdf" or "epub"
    source_path: Optional[Path] = None
    total_pages: int = 0
    front_matter: str = ""
    back_matter: str = ""
    chapters: List[Chapter] = field(default_factory=list)

    @property
    def total_words(self) -> int:
        return sum(ch.word_count for ch in self.chapters)

    @property
    def total_scenes(self) -> int:
        return sum(len(ch.scenes) for ch in self.chapters)
