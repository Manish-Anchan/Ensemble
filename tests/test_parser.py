import pytest
import pymupdf
from pathlib import Path

from ensemble.parser.cleaner import (
    normalize_typography,
    repair_hyphenation,
    unwrap_paragraphs,
    strip_running_artifacts,
    clean_fiction_prose,
)
from ensemble.parser.chunker import split_into_scenes
from ensemble.parser.extractor import load_book


def test_typography_normalization():
    raw = '“Listen to me,” he whispered, ‘don’t move’—not yet…'
    cleaned = normalize_typography(raw)
    assert '"Listen to me," he whispered' in cleaned
    assert "'don't move'" in cleaned
    assert " — " in cleaned
    assert "..." in cleaned


def test_hyphenation_repair():
    raw = "The detec-\ntive examined the ske-\nletal remains."
    repaired = repair_hyphenation(raw)
    assert "detective" in repaired
    assert "skeletal" in repaired


def test_paragraph_unwrapping():
    raw = """
    This is line one of the first
    paragraph which spans across
    multiple lines in print.

    This is the second paragraph.
    It also spans lines.
    """
    unwrapped = unwrap_paragraphs(raw)
    paras = unwrapped.split("\n\n")
    assert len(paras) == 2
    assert paras[0] == "This is line one of the first paragraph which spans across multiple lines in print."
    assert paras[1] == "This is the second paragraph. It also spans lines."


def test_strip_running_artifacts():
    lines = [
        "A STUDY IN SCARLET",
        "Chapter 1",
        "Mr. Sherlock Holmes sat by the fire.",
        "42",
        "- 43 -",
        "xiv",
    ]
    recurring = {"a study in scarlet"}
    cleaned = strip_running_artifacts(lines, recurring_patterns=recurring)
    assert "A STUDY IN SCARLET" not in cleaned
    assert "42" not in cleaned
    assert "- 43 -" not in cleaned
    assert "xiv" not in cleaned
    assert "Chapter 1" in cleaned
    assert "Mr. Sherlock Holmes sat by the fire." in cleaned


def test_scene_chunker_with_delimiters():
    text = """
    Arthur stopped at the edge of the clearing. The air smelled of old ash.

    * * *

    Two hours later, Elena reached the mountain pass. The wind was relentless.
    """
    scenes = split_into_scenes(text, chapter_index=1, min_words=10, target_words=50)
    assert len(scenes) == 2
    assert "Arthur stopped" in scenes[0].text
    assert "Elena reached" in scenes[1].text


def test_pdf_spatial_clipping_and_toc(tmp_path: Path):
    """
    Creates a synthetic 3-page PDF with:
    - Top header: 'The Whispering Shadows' (at y=20)
    - Bottom footer: 'Page 1', 'Page 2', 'Page 3' (at y=760)
    - Body text: between y=100 and y=700
    - Embedded TOC bookmarks for Chapter 1 and Chapter 2
    """
    pdf_path = tmp_path / "test_book.pdf"
    doc = pymupdf.open()

    # Page 1: Chapter 1 start
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text(pymupdf.Point(200, 25), "The Whispering Shadows", fontsize=10) # Header (top margin)
    p1.insert_text(pymupdf.Point(50, 100), "CHAPTER 1: THE DISCOVERY\n\nArthur entered the dark room. He saw the sha-\ndow on the wall.", fontsize=12)
    p1.insert_text(pymupdf.Point(280, 810), "1", fontsize=10) # Footer (bottom margin)

    # Page 2: Chapter 1 continuation
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text(pymupdf.Point(200, 25), "The Whispering Shadows", fontsize=10)
    p2.insert_text(pymupdf.Point(50, 100), "Elena was already waiting. 'You are late,' she said.\n\nHe smiled faintly.", fontsize=12)
    p2.insert_text(pymupdf.Point(280, 810), "2", fontsize=10)

    # Page 3: Chapter 2
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text(pymupdf.Point(200, 25), "The Whispering Shadows", fontsize=10)
    p3.insert_text(pymupdf.Point(50, 100), "CHAPTER 2: THE ESCAPE\n\nThey ran through the rain toward the carriage.", fontsize=12)
    p3.insert_text(pymupdf.Point(280, 810), "3", fontsize=10)

    # Add TOC: [level, title, page_number (1-based)]
    doc.set_toc([
        [1, "Chapter 1: The Discovery", 1],
        [1, "Chapter 2: The Escape", 3],
    ])
    doc.save(str(pdf_path))
    doc.close()

    # Parse with our PDF extractor
    book = load_book(pdf_path, header_margin_pt=45.0, footer_margin_pt=45.0)

    assert book.total_pages == 3
    assert len(book.chapters) == 2
    assert book.chapters[0].title == "Chapter 1: The Discovery"
    assert book.chapters[1].title == "Chapter 2: The Escape"

    ch1_text = book.chapters[0].clean_text
    ch2_text = book.chapters[1].clean_text

    # Verify spatial margin clipping stripped the header and footer!
    assert "The Whispering Shadows" not in ch1_text
    assert "The Whispering Shadows" not in ch2_text
    assert "1" not in ch1_text.split()  # No standalone page number
    assert "2" not in ch1_text.split()

    # Verify hyphenation repair
    assert "shadow" in ch1_text

    # Verify dialogue and characters are preserved
    assert "Arthur entered the dark room" in ch1_text
    assert "Elena was already waiting" in ch1_text
    assert "They ran through the rain" in ch2_text


def test_pdf_regex_detection_without_toc(tmp_path: Path):
    """
    Tests PDF chapter extraction when no TOC bookmarks are present in the PDF.
    """
    pdf_path = tmp_path / "test_no_toc.pdf"
    doc = pymupdf.open()

    p1 = doc.new_page(width=595, height=842)
    p1.insert_text(pymupdf.Point(50, 100), "Chapter 1\n\nIt was the best of times.", fontsize=12)

    p2 = doc.new_page(width=595, height=842)
    p2.insert_text(pymupdf.Point(50, 100), "Chapter 2\n\nIt was the worst of times.", fontsize=12)

    doc.save(str(pdf_path))
    doc.close()

    book = load_book(pdf_path)
    assert len(book.chapters) == 2
    assert "best of times" in book.chapters[0].clean_text
    assert "worst of times" in book.chapters[1].clean_text


def test_epub_extraction():
    """
    Tests EPUB parsing against a real book (The Time Machine).
    """
    sample_path = Path(__file__).parent.parent / "samples" / "the_time_machine.epub"
    if not sample_path.exists():
        pytest.skip("Sample EPUB not found")

    book = load_book(sample_path)
    assert book.format == "epub"
    assert "Time Machine" in book.title
    assert "Wells" in book.author
    assert len(book.chapters) > 10
    # First story chapter
    assert "Introduction" in book.chapters[0].title
    assert "Time Traveller" in book.chapters[0].clean_text
    assert len(book.chapters[0].scenes) >= 1


def test_drop_cap_stitching():
    """
    Tests drop cap reconnection for both word fragments (In, There)
    and standalone words (I couldn't, A dark night).
    """
    from ensemble.parser.cleaner import stitch_drop_cap

    # Fragments
    assert stitch_drop_cap("I", "n my younger years") == "In my younger years"
    assert stitch_drop_cap("A", "bout half way") == "About half way"
    assert stitch_drop_cap("T", "here was music") == "There was music"
    assert stitch_drop_cap("W", "hen I came home") == "When I came home"
    assert stitch_drop_cap("A", "fter two years") == "After two years"

    # Standalone single-letter words
    assert stitch_drop_cap("I", "couldn't sleep all night") == "I couldn't sleep all night"
    assert stitch_drop_cap("I", "remember the first time") == "I remember the first time"
    assert stitch_drop_cap("A", "dark and stormy night") == "A dark and stormy night"
