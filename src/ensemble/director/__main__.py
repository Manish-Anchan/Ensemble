import argparse
import sys
import json
from pathlib import Path

from ensemble.parser.extractor import load_book
from ensemble.producer.models import CastSheet, CharacterProfile
from ensemble.director.director import SceneDirector


def main():
    parser = argparse.ArgumentParser(
        description="Ensemble Scene Director: Adapt Novel Prose into Dramatic Screenplay"
    )
    parser.add_argument("file", help="Path to PDF or EPUB book file")
    parser.add_argument(
        "--chapter",
        type=int,
        default=1,
        help="Chapter number (1-indexed, default: 1)",
    )
    parser.add_argument(
        "--scene",
        type=int,
        default=1,
        help="Scene index in the chapter (1-indexed, default: 1)",
    )
    parser.add_argument(
        "--cast",
        type=str,
        default=None,
        help="Path to cast_sheet.json (default: <book_stem>_cast.json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to save screenplay JSON (default: outputs/<book_stem>_ch<chapter>_s<scene>_screenplay.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw screenplay JSON to stdout",
    )

    args = parser.parse_args()
    path = Path(args.file)
    if not path.exists():
        print(f"❌ Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)

    book = load_book(path)
    ch_idx = args.chapter - 1
    if ch_idx < 0 or ch_idx >= len(book.chapters):
        print(f"❌ Error: Chapter {args.chapter} does not exist.", file=sys.stderr)
        sys.exit(1)

    chapter = book.chapters[ch_idx]
    s_idx = args.scene - 1
    if s_idx < 0 or s_idx >= len(chapter.scenes):
        print(f"❌ Error: Scene {args.scene} does not exist (chapter has {len(chapter.scenes)} scenes).", file=sys.stderr)
        sys.exit(1)

    target_scene = chapter.scenes[s_idx]

    # Load cast sheet if available
    cast_path = Path(args.cast) if args.cast else path.with_name(f"{path.stem}_cast.json")
    if cast_path.exists():
        cast_sheet = CastSheet.load_json(cast_path)
    else:
        cast_sheet = CastSheet(book_title=book.title, characters={
            "narrator": CharacterProfile(
                id="narrator",
                name="Narrator",
                gender="male",
                age_group="adult",
                role="narrator",
                personality_traits=["observant"],
                aliases=["narrator"],
                voice_id="bm_george",
            )
        })

    director = SceneDirector()
    screenplay, updated_cast = director.direct_scene(target_scene, cast_sheet=cast_sheet)

    if args.json:
        print(screenplay.to_json())
        return

    print("=" * 70)
    print(f"🎬 ENSEMBLE SCENE DIRECTOR: {book.title}")
    print(f"📖 Chapter {args.chapter}: '{chapter.title}' • Scene {args.scene} ({target_scene.word_count} words)")
    print(f"🎭 Total Directed Lines: {len(screenplay.lines)}")
    print("=" * 70 + "\n")

    for i, line in enumerate(screenplay.lines, 1):
        voice = cast_sheet.get_voice_for_speaker(line.speaker)
        role = line.speaker.upper()
        print(f"[{i:02d}] 🎭 {role:<15} ({voice} | emotion: {line.emotion} | speed: {line.speed:.2f}x | pause: {line.pause_after_ms}ms)")
        print(f"     \"{line.text}\"\n")

    # Save output JSON
    out_dir = Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = Path(args.output) if args.output else out_dir / f"{path.stem}_ch{args.chapter}_s{args.scene}_screenplay.json"
    out_file.write_text(screenplay.to_json(), encoding="utf-8")

    print("=" * 70)
    print(f"💾 Screenplay saved to: {out_file.resolve()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
