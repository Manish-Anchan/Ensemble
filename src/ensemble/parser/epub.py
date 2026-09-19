from pathlib import Path
from typing import List, Tuple
import pymupdf

from ensemble.parser.models import Book, Chapter
from ensemble.parser.cleaner import clean_fiction_prose, unwrap_block, merge_page_paragraphs
from ensemble.parser.chunker import split_into_scenes


class EPUBBookExtractor:
    """
    EPUB extractor leveraging PyMuPDF's native document engine.
    Extracts structured chapters via TOC outlines and segments into scenes.
    """

    def __init__(self, target_scene_words: int = 600):
        self.target_scene_words = target_scene_words

    def extract(self, file_path: str | Path) -> Book:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"EPUB file not found: {path}")

        doc = pymupdf.open(str(path))
        num_pages = len(doc)
        metadata = doc.metadata or {}

        title = metadata.get("title") or path.stem.replace("_", " ").title()
        author = metadata.get("author") or "Unknown"

        toc = doc.get_toc()
        chapters: List[Chapter] = []

        front_matter_parts = []
        if toc:
            # EPUB with valid TOC
            for idx, item in enumerate(toc):
                lvl, ch_title, start_page = item[0], item[1].strip(), item[2]
                if lvl > 2:  # Stick to top-level or sub-level chapters
                    continue

                ch_lower = ch_title.lower()
                # Skip front matter entries
                if (
                    any(fm in ch_lower for fm in ("contents", "table of contents", "copyright", "title page", "cover", "colophon"))
                    or ch_lower == title.lower()
                ):
                    # Save into front matter
                    if start_page <= num_pages:
                        fm_txt = doc[max(0, start_page - 1)].get_text("text")
                        if fm_txt.strip():
                            front_matter_parts.append(fm_txt)
                    continue

                # Stop if back matter reached
                if any(bm in ch_lower for bm in ("about the author", "afterword", "license", "gutenberg")):
                    break

                p_start_0 = max(0, start_page - 1)
                if idx + 1 < len(toc):
                    p_end_0 = min(toc[idx + 1][2] - 1, num_pages)
                else:
                    p_end_0 = num_pages

                pages_paras = []
                for p_num in range(p_start_0, p_end_0):
                    blocks = doc[p_num].get_text("blocks")
                    paras = [unwrap_block(b[4]) for b in blocks if b[6] == 0 and b[4].strip()]
                    if paras:
                        pages_paras.append(paras)

                clean = merge_page_paragraphs(pages_paras)
                if not clean.strip():
                    continue

                # Strip redundant leading chapter title from prose if present
                if clean.lower().startswith(ch_title.lower()):
                    clean = clean[len(ch_title):].lstrip(" :\n—.-")

                scenes = split_into_scenes(
                    clean,
                    chapter_index=len(chapters) + 1,
                    target_words=self.target_scene_words
                )

                chapters.append(
                    Chapter(
                        index=len(chapters) + 1,
                        title=ch_title,
                        raw_text=clean,
                        clean_text=clean,
                        page_start=start_page,
                        page_end=p_end_0,
                        scenes=scenes
                    )
                )

        if not chapters:
            # Fallback: Extract all pages and chunk
            pages_paras = []
            for i in range(num_pages):
                blocks = doc[i].get_text("blocks")
                paras = [unwrap_block(b[4]) for b in blocks if b[6] == 0 and b[4].strip()]
                if paras:
                    pages_paras.append(paras)

            clean = merge_page_paragraphs(pages_paras)
            scenes = split_into_scenes(clean, chapter_index=1, target_words=self.target_scene_words)
            chapters.append(
                Chapter(
                    index=1,
                    title="Chapter 1",
                    raw_text=clean,
                    clean_text=clean,
                    page_start=1,
                    page_end=num_pages,
                    scenes=scenes
                )
            )

        doc.close()

        return Book(
            title=title,
            author=author,
            format="epub",
            source_path=path,
            total_pages=num_pages,
            front_matter=clean_fiction_prose("\n\n".join(front_matter_parts)),
            chapters=chapters
        )
