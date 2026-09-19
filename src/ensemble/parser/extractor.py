from pathlib import Path
from ensemble.parser.models import Book
from ensemble.parser.pdf import PDFBookExtractor
from ensemble.parser.epub import EPUBBookExtractor


def load_book(
    file_path: str | Path,
    header_margin_pt: float = 45.0,
    footer_margin_pt: float = 45.0,
    target_scene_words: int = 600,
) -> Book:
    """
    Unified entry point for loading and parsing fiction books (PDF / EPUB).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Book file does not exist: {path}")

    ext = path.suffix.lower()
    if ext == ".pdf":
        extractor = PDFBookExtractor(
            header_margin_pt=header_margin_pt,
            footer_margin_pt=footer_margin_pt,
            target_scene_words=target_scene_words,
        )
        return extractor.extract(path)
    elif ext in (".epub", ".mobi"):
        extractor = EPUBBookExtractor(
            target_scene_words=target_scene_words,
        )
        return extractor.extract(path)
    else:
        raise ValueError(f"Unsupported book format '{ext}'. Expected .pdf or .epub.")
