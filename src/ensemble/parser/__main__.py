import argparse
import sys
import time
from pathlib import Path
from ensemble.parser.extractor import load_book


def main():
    parser = argparse.ArgumentParser(
        description="Ensemble Book Ingestion & Parsing Inspector"
    )
    parser.add_argument("file", help="Path to PDF or EPUB book file")
    parser.add_argument(
        "--preview-ch",
        type=int,
        default=None,
        help="Preview clean text and scene chunks for a specific chapter index (1-based)",
    )
    parser.add_argument(
        "--header-margin",
        type=float,
        default=45.0,
        help="Top margin (points) to clip running headers (PDF only)",
    )
    parser.add_argument(
        "--footer-margin",
        type=float,
        default=45.0,
        help="Bottom margin (points) to clip footers/page numbers (PDF only)",
    )
    parser.add_argument(
        "--target-words",
        type=int,
        default=600,
        help="Target scene chunk word count",
    )

    args = parser.parse_args()
    path = Path(args.file)
    if not path.exists():
        print(f"❌ Error: File not found: {path}")
        sys.exit(1)

    print("=" * 65)
    print("📖 ENSEMBLE: Book Ingestion & Parsing Engine")
    print("=" * 65)
    print(f"Loading '{path.name}'...")

    t0 = time.time()
    try:
        book = load_book(
            path,
            header_margin_pt=args.header_margin,
            footer_margin_pt=args.footer_margin,
            target_scene_words=args.target_words,
        )
    except Exception as e:
        print(f"❌ Extraction error: {e}")
        sys.exit(1)
    dur = time.time() - t0

    print(f"\n✨ Extracted in {dur * 1000:.1f}ms ({dur:.2f}s)")
    print(f"Title:        {book.title}")
    print(f"Author:       {book.author}")
    print(f"Format:       {book.format.upper()}")
    print(f"Total Pages:  {book.total_pages}")
    print(f"Story Words:  {book.total_words:,} words")
    print(f"Chapters:     {len(book.chapters)}")
    print(f"Total Scenes: {book.total_scenes}")

    if book.front_matter:
        fm_words = len(book.front_matter.split())
        print(f"Front Matter: {fm_words} words (isolated from narration)")

    print("\n📑 Chapter Breakdown:")
    print("-" * 65)
    for ch in book.chapters:
        print(
            f"  [{ch.index:02d}] {ch.title:<35} | {ch.word_count:>5} words | {len(ch.scenes):>2} scenes | pp. {ch.page_start}-{ch.page_end}"
        )

    if args.preview_ch is not None:
        ch_idx = args.preview_ch - 1
        if 0 <= ch_idx < len(book.chapters):
            ch = book.chapters[ch_idx]
            print("\n" + "=" * 65)
            print(f"🔍 PREVIEW: Chapter {ch.index} — {ch.title}")
            print("=" * 65)
            for sc in ch.scenes:
                print(f"\n--- Scene {sc.scene_index} ({sc.word_count} words) ---")
                preview_snippet = sc.text[:350] + ("..." if len(sc.text) > 350 else "")
                print(preview_snippet)
        else:
            print(f"\n⚠️  Chapter {args.preview_ch} does not exist (1 to {len(book.chapters)} available).")


if __name__ == "__main__":
    main()
