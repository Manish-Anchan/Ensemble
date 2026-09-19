import re
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
import pymupdf

from ensemble.parser.models import Book, Chapter
from ensemble.parser.cleaner import (
    clean_fiction_prose,
    join_page_texts,
    unwrap_block,
    merge_page_paragraphs,
    stitch_drop_cap,
)
from ensemble.parser.chunker import split_into_scenes


# Chapter heading regex patterns for fiction
CHAPTER_REGEX = re.compile(
    r"^(?:(?:CHAPTER|Chapter)\s+(?:\d+|[IVXLCDM]+|[A-Za-z]+)|PROLOGUE|Prologue|EPILOGUE|Epilogue|ACT\s+[IVXLCDM]+)"
    r"(?:\s*[:.\-—]\s*(.*))?$",
    re.MULTILINE
)

# Front matter keywords (to identify non-story introductory pages)
FRONT_MATTER_KEYWORDS = {
    "table of contents", "contents", "copyright", "all rights reserved",
    "isbn", "published by", "dedication", "epigraph", "title page"
}

# Back matter keywords (to cut off post-story author notes)
BACK_MATTER_REGEX = re.compile(
    r"^(?:ABOUT THE AUTHOR|About the Author|ACKNOWLEDGMENTS|Acknowledgments|"
    r"DISCUSSION QUESTIONS|Discussion Questions|NOTE FROM THE AUTHOR|AFTERWORD|Afterword)\b",
    re.MULTILINE
)


class PDFBookExtractor:
    """
    High-performance PDF extractor for fiction novels using PyMuPDF.
    Performs spatial margin clipping to eliminate running headers/footers,
    detects chapters via outlines or regex, and segments into scene chunks.
    """

    def __init__(
        self,
        header_margin_pt: float = 45.0,
        footer_margin_pt: float = 45.0,
        target_scene_words: int = 600,
    ):
        self.header_margin = header_margin_pt
        self.footer_margin = footer_margin_pt
        self.target_scene_words = target_scene_words

    def _discover_recurring_headers(self, doc: pymupdf.Document, sample_pages: int = 30) -> Set[str]:
        """
        Samples the header/footer zones across multiple pages to detect
        recurring strings (e.g. Author Name, Book Title) that might bleed in.
        """
        line_counts: Dict[str, int] = {}
        total = min(len(doc), sample_pages)
        if total == 0:
            return set()

        for i in range(total):
            page = doc[i]
            rect = page.rect
            # Sample proportional top/bottom margins (15% of page height or min 70pt)
            margin_h = max(70.0, rect.height * 0.15)
            top_clip = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + margin_h)
            bottom_clip = pymupdf.Rect(rect.x0, rect.y1 - margin_h, rect.x1, rect.y1)

            top_text = page.get_text("text", clip=top_clip)
            bottom_text = page.get_text("text", clip=bottom_clip)

            for raw_line in (top_text + "\n" + bottom_text).split("\n"):
                stripped = raw_line.strip().lower()
                # Ignore pure numbers or single glyphs
                if stripped and not stripped.isdigit() and len(stripped) > 3:
                    line_counts[stripped] = line_counts.get(stripped, 0) + 1

        # Any line appearing on > 20% of sampled pages is a recurring artifact
        threshold = max(3, int(total * 0.20))
        return {line for line, count in line_counts.items() if count >= threshold}

    def _extract_page_paras(
        self,
        page: pymupdf.Page,
        recurring_patterns: Set[str]
    ) -> List[str]:
        """
        Extracts paragraphs (blocks) within the body area, excluding headers & footers.
        """
        rect = page.rect
        clip = pymupdf.Rect(
            rect.x0,
            rect.y0 + self.header_margin,
            rect.x1,
            rect.y1 - self.footer_margin
        )
        blocks = page.get_text("blocks", clip=clip)
        page_paras = []
        # Multi-character roman numerals (e.g. iv, xiv, xii) or digits, never lone letters like 'I' or 'A'
        page_num_regex = re.compile(r"^\s*[-—~]?\s*(\d+|[ivxlcdm]{2,})\s*[-—~]?\s*$", re.IGNORECASE)
        drop_cap = ""

        for b in blocks:
            if b[6] != 0:
                continue
            raw_text = b[4].strip()
            if not raw_text:
                continue
            if page_num_regex.match(raw_text):
                continue
            if recurring_patterns and raw_text.lower() in recurring_patterns:
                continue

            unwrapped = unwrap_block(raw_text)
            if not unwrapped:
                continue

            # Check if this block is an isolated drop-cap initial (1 uppercase letter)
            if len(unwrapped) == 1 and unwrapped.isupper():
                drop_cap = unwrapped
                continue

            if drop_cap:
                unwrapped = stitch_drop_cap(drop_cap, unwrapped)
                drop_cap = ""

            page_paras.append(unwrapped)

        return page_paras

    def _extract_by_toc(
        self,
        doc: pymupdf.Document,
        toc: List[Tuple[int, str, int]],
        recurring_patterns: Set[str]
    ) -> List[Chapter]:
        """
        Extracts chapters when the PDF contains a valid embedded Table of Contents (outlines).
        """
        filtered_toc = []
        doc_title_lower = (doc.metadata.get("title") or "").strip().lower()
        num_pages = len(doc)

        for item in toc:
            lvl, title, page_num = item[0], item[1].strip(), item[2]
            title_lower = title.lower()

            if page_num <= 0 or page_num > num_pages:
                continue
            if any(fm in title_lower for fm in FRONT_MATTER_KEYWORDS):
                continue
            if doc_title_lower and title_lower == doc_title_lower and page_num <= 2:
                continue
            if BACK_MATTER_REGEX.search(title):
                break

            filtered_toc.append((title, page_num))

        if not filtered_toc:
            return []

        chapters: List[Chapter] = []

        for idx, (title, start_page) in enumerate(filtered_toc):
            p_start_0 = start_page - 1
            if p_start_0 >= num_pages:
                continue

            if idx + 1 < len(filtered_toc):
                p_end_0 = min(filtered_toc[idx + 1][1] - 1, num_pages)
            else:
                p_end_0 = num_pages

            chapter_pages_paras = []
            for p_num in range(p_start_0, p_end_0):
                paras = self._extract_page_paras(doc[p_num], recurring_patterns)
                if paras:
                    chapter_pages_paras.append(paras)

            clean_text = merge_page_paragraphs(chapter_pages_paras)

            # Strip leading title repetition in body if it matches TOC title
            if clean_text.lower().startswith(title.lower()):
                clean_text = clean_text[len(title):].lstrip(" :\n—.-")

            scenes = split_into_scenes(
                clean_text,
                chapter_index=idx + 1,
                target_words=self.target_scene_words
            )

            chapters.append(
                Chapter(
                    index=idx + 1,
                    title=title,
                    raw_text=clean_text,
                    clean_text=clean_text,
                    page_start=start_page,
                    page_end=p_end_0,
                    scenes=scenes
                )
            )

        return chapters

    def _extract_by_regex(
        self,
        doc: pymupdf.Document,
        recurring_patterns: Set[str]
    ) -> List[Chapter]:
        """
        Extracts chapters by scanning page text for chapter heading patterns.
        Used when the PDF has no embedded TOC bookmarks.
        """
        num_pages = len(doc)
        pages_paras: List[Tuple[int, List[str]]] = []

        for i in range(num_pages):
            paras = self._extract_page_paras(doc[i], recurring_patterns)
            pages_paras.append((i + 1, paras))

        # Identify chapter start locations
        chapter_starts: List[Tuple[str, int, int]] = []  # (title, page_idx, para_idx)

        for p_num, paras in pages_paras:
            for p_idx, para in enumerate(paras):
                match = CHAPTER_REGEX.match(para)
                if match:
                    title = match.group(0).strip()
                    chapter_starts.append((title, p_num, p_idx))
                    break

        if not chapter_starts:
            all_paras = [p for _, paras in pages_paras for p in paras]
            clean = merge_page_paragraphs([all_paras])
            scenes = split_into_scenes(clean, chapter_index=1, target_words=self.target_scene_words)
            return [
                Chapter(
                    index=1,
                    title="Chapter 1",
                    raw_text=clean,
                    clean_text=clean,
                    page_start=1,
                    page_end=num_pages,
                    scenes=scenes
                )
            ]

        chapters: List[Chapter] = []
        for idx, (title, start_page, _) in enumerate(chapter_starts):
            if idx + 1 < len(chapter_starts):
                end_page = chapter_starts[idx + 1][1]
            else:
                end_page = num_pages

            ch_pages_paras = []
            for p_num in range(start_page - 1, end_page):
                paras = pages_paras[p_num][1]
                if paras:
                    ch_pages_paras.append(paras)

            clean = merge_page_paragraphs(ch_pages_paras)

            if clean.lower().startswith(title.lower()):
                clean = clean[len(title):].lstrip(" :\n—.-")

            scenes = split_into_scenes(
                clean,
                chapter_index=idx + 1,
                target_words=self.target_scene_words
            )

            chapters.append(
                Chapter(
                    index=idx + 1,
                    title=title,
                    raw_text=clean,
                    clean_text=clean,
                    page_start=start_page,
                    page_end=end_page,
                    scenes=scenes
                )
            )

        return chapters

    def extract(self, file_path: str | Path) -> Book:
        """
        Parses a PDF fiction book into structured Chapters and Scenes.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Book file not found: {path}")

        doc = pymupdf.open(str(path))
        num_pages = len(doc)
        metadata = doc.metadata or {}

        title = metadata.get("title") or path.stem.replace("_", " ").title()
        author = metadata.get("author") or "Unknown"

        # 1. Discover recurring running headers/footers
        recurring = self._discover_recurring_headers(doc)

        # 2. Check for embedded Table of Contents
        toc = doc.get_toc()
        chapters = []
        if toc:
            chapters = self._extract_by_toc(doc, toc, recurring)

        # 3. If TOC was absent or produced no chapters, fall back to regex scanning
        if not chapters:
            chapters = self._extract_by_regex(doc, recurring)

        # 4. Separate front matter (pages before Chapter 1)
        front_matter = ""
        if chapters and chapters[0].page_start > 1:
            front_pages = []
            for p in range(0, chapters[0].page_start - 1):
                paras = self._extract_page_paras(doc[p], recurring)
                if paras:
                    front_pages.append(paras)
            front_matter = merge_page_paragraphs(front_pages)

        doc.close()

        return Book(
            title=title,
            author=author,
            format="pdf",
            source_path=path,
            total_pages=num_pages,
            front_matter=front_matter,
            chapters=chapters
        )
