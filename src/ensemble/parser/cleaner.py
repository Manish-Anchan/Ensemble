import re
import unicodedata
from typing import List, Set


def normalize_typography(text: str) -> str:
    """
    Normalizes typographic quotes, dashes, and ligatures to standard forms.
    """
    # Normalize unicode ligatures (e.g. fi, fl)
    text = unicodedata.normalize("NFKD", text)

    # Standardize curly quotes and apostrophes
    replacements = {
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "’": "'",
        "‘": "'",
        "`": "'",
        "–": " — ",     # En-dash to spaced em-dash
        "—": " — ",     # Ensure em-dash has comfortable spacing for TTS
        "…": "...",
        "\u00a0": " ",  # Non-breaking space
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Clean double spaces caused by dash padding
    text = re.sub(r"[ \t]+", " ", text)
    return text


def repair_hyphenation(text: str) -> str:
    """
    Rejoins words split across line breaks by a hyphen.
    e.g. 'inves-\\ntigation' -> 'investigation'
    """
    # Matches a word character, a hyphen at the end of a line, then word continuation
    # e.g. 'skele-\ntal' -> 'skeletal'
    return re.sub(r"(\b[A-Za-z]+)-\s*\n\s*([a-z]+)\b", r"\1\2", text)


def unwrap_paragraphs(text: str) -> str:
    """
    Converts hard line breaks inside a paragraph into spaces while
    preserving paragraph breaks (double newlines).
    """
    # First normalize newlines to standard \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Split into raw paragraphs by two or more newlines
    raw_paragraphs = re.split(r"\n\s*\n+", text)
    cleaned_paragraphs = []

    for para in raw_paragraphs:
        lines = para.split("\n")
        # Strip leading/trailing whitespace on each line
        stripped_lines = [line.strip() for line in lines if line.strip()]
        if not stripped_lines:
            continue

        # Join lines in paragraph with a single space
        joined_para = " ".join(stripped_lines)
        # Collapse any internal multiple spaces
        joined_para = re.sub(r"\s+", " ", joined_para)
        cleaned_paragraphs.append(joined_para)

    return "\n\n".join(cleaned_paragraphs)


def strip_running_artifacts(lines: List[str], recurring_patterns: Set[str] = None) -> List[str]:
    """
    Strips isolated page numbers and recurring headers/footers from a list of lines.
    """
    clean_lines = []
    page_num_regex = re.compile(r"^\s*[-—~]?\s*(\d+|[ivxlcdm]+)\s*[-—~]?\s*$", re.IGNORECASE)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Skip lone page numbers
        if page_num_regex.match(stripped):
            continue

        # Skip known recurring header strings (e.g. book title or author name)
        if recurring_patterns and stripped.lower() in recurring_patterns:
            continue

        clean_lines.append(stripped)

    return clean_lines


def join_page_texts(pages: List[str]) -> str:
    """
    Joins text blocks from consecutive book pages, distinguishing between
    sentences/paragraphs flowing across page boundaries versus true paragraph breaks.
    """
    if not pages:
        return ""

    joined: List[str] = []
    for page in pages:
        stripped = page.strip()
        if not stripped:
            continue

        if not joined:
            joined.append(stripped)
            continue

        prev = joined[-1]
        # Check if previous page ended mid-sentence (no terminal punctuation)
        # or with a hyphen, or if the next page continues in lowercase
        ends_with_terminal = bool(re.search(r'[.?!]["\']?\s*$', prev))
        starts_with_lowercase = stripped[0].islower()

        if not ends_with_terminal or starts_with_lowercase:
            # Continues mid-paragraph across page boundary
            joined.append("\n" + stripped)
        else:
            # True paragraph break between pages
            joined.append("\n\n" + stripped)

    return "".join(joined)


def unwrap_block(block_text: str) -> str:
    """
    Unwraps hard line breaks within a single block/paragraph into spaces,
    after repairing hyphenation and normalizing typography.
    """
    text = normalize_typography(block_text)
    text = repair_hyphenation(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    joined = " ".join(lines)
    return re.sub(r"\s+", " ", joined).strip()


def merge_page_paragraphs(pages_paras: List[List[str]]) -> str:
    """
    Merges lists of paragraphs from consecutive pages, joining any sentence
    that was severed across a page break into the same paragraph.
    """
    combined: List[str] = []
    for page_paras in pages_paras:
        for para in page_paras:
            p = para.strip()
            if not p:
                continue
            if not combined:
                combined.append(p)
                continue

            prev = combined[-1]
            ends_with_terminal = bool(re.search(r'[.?!]["\']?\s*$', prev))
            starts_with_lowercase = p[0].islower()

            if not ends_with_terminal or starts_with_lowercase:
                # Merge into previous paragraph
                combined[-1] = prev + " " + p
            else:
                combined.append(p)

    return "\n\n".join(combined)


def stitch_drop_cap(drop_cap: str, text: str) -> str:
    """
    Reconnects a standalone drop-cap initial letter to the following paragraph text.
    Correctly distinguishes between single-letter words ('I', 'A') followed by full words
    versus word fragments ('In', 'About', 'There', 'When').
    """
    first_token = text.split()[0] if text.split() else ""
    combined = (drop_cap + first_token).lower()

    # Common words starting with I or A that frequently open fiction chapters
    common_i_words = {"in", "it", "if", "is", "into", "its", "inside", "indeed", "instead", "immediately"}
    common_a_words = {
        "about", "after", "at", "as", "and", "all", "although", "again",
        "along", "around", "across", "almost", "already", "an"
    }

    if drop_cap == "I":
        if combined in common_i_words:
            return drop_cap + text
        return f"{drop_cap} {text}"
    elif drop_cap == "A":
        if combined in common_a_words:
            return drop_cap + text
        return f"{drop_cap} {text}"
    else:
        # The other 24 letters are never standalone English words
        return drop_cap + text


def clean_fiction_prose(text: str, recurring_patterns: Set[str] = None) -> str:
    """
    End-to-end prose cleaner for fiction text extracted from PDFs or EPUBs.
    """
    text = normalize_typography(text)
    text = repair_hyphenation(text)

    if recurring_patterns:
        lines = text.split("\n")
        lines = strip_running_artifacts(lines, recurring_patterns)
        text = "\n".join(lines)

    text = unwrap_paragraphs(text)
    return text.strip()
