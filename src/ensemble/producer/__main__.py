import argparse
import sys
import time
from pathlib import Path
from ensemble.parser.extractor import load_book
from ensemble.producer.casting import CastingProducer


def main():
    parser = argparse.ArgumentParser(
        description="Ensemble Casting Producer: Autonomous Character Discovery & Voice Casting"
    )
    parser.add_argument("file", help="Path to PDF or EPUB book file")
    parser.add_argument(
        "--chapters",
        type=int,
        default=1,
        help="Number of opening chapters to sample for casting (default: 1)",
    )
    parser.add_argument(
        "--footer-margin",
        type=float,
        default=75.0,
        help="Bottom margin (points) for PDF layout clipping",
    )
    parser.add_argument(
        "--scenes",
        type=int,
        default=0,
        help="Max scenes to process per chapter (default: 0 = all scenes in chapter)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to save output cast_sheet.json (default: <book_name>_cast.json)",
    )

    args = parser.parse_args()
    path = Path(args.file)
    if not path.exists():
        print(f"❌ Error: File not found: {path}")
        sys.exit(1)

    print("=" * 65)
    print("🎭 ENSEMBLE: The Casting Producer (Scene-by-Scene Pipeline)")
    print("=" * 65)
    print(f"Loading '{path.name}'...")

    try:
        book = load_book(path, footer_margin_pt=args.footer_margin)
    except Exception as e:
        print(f"❌ Book loading error: {e}")
        sys.exit(1)

    if not book.chapters:
        print("❌ Error: No chapters detected in book.")
        sys.exit(1)

    sampled_chapters = book.chapters[:args.chapters]
    total_scenes_count = sum(len(ch.scenes if not args.scenes else ch.scenes[:args.scenes]) for ch in sampled_chapters)
    print(f"📖 Book: '{book.title}' by {book.author}")
    print(f"🎬 Sequential casting pipeline across {len(sampled_chapters)} chapter(s) ({total_scenes_count} scenes total)...")

    producer = CastingProducer()
    cast_sheet = None
    t_start = time.time()
    out_path = Path(args.output) if args.output else path.with_name(f"{path.stem}_cast.json")

    for idx, ch in enumerate(sampled_chapters, start=1):
        scenes_to_process = ch.scenes
        if args.scenes and args.scenes > 0:
            scenes_to_process = ch.scenes[:args.scenes]

        print(f"\n📖 [Chapter {idx}/{len(sampled_chapters)}] '{ch.title}' ({len(scenes_to_process)} scenes, {ch.word_count:,} words)")

        for s_idx, scene in enumerate(scenes_to_process, start=1):
            t0 = time.time()
            try:
                cast_sheet, new_chars = producer.cast_scene(
                    book_title=book.title,
                    scene_text=scene.text,
                    scene_index=s_idx,
                    total_scenes=len(scenes_to_process),
                    existing_cast_sheet=cast_sheet,
                )
            except Exception as e:
                print(f"❌ Casting error on scene {s_idx}: {e}")
                sys.exit(1)
            dur = time.time() - t0
            cast_sheet.save_json(out_path)

            new_str = ""
            if new_chars:
                new_str = " | 🌟 Discovered: " + ", ".join(f"{c.name} ({c.voice_id})" for c in new_chars)
            print(f"   🎬 [Scene {s_idx}/{len(scenes_to_process)}] ({scene.word_count} words, {dur:.2f}s) Cast: {len(cast_sheet.characters)}{new_str}")

    total_dur = time.time() - t_start
    print(f"\n✨ Sequential casting completed in {total_dur:.2f}s!")
    print(f"Total Cast Members: {len(cast_sheet.characters)}\n")

    print("=" * 65)
    print(f"📋 MASTER CAST SHEET: {cast_sheet.book_title}")
    print("=" * 65)

    for cid, char in cast_sheet.characters.items():
        role_tag = f"[{char.role.upper()}]"
        traits = ", ".join(char.personality_traits) if char.personality_traits else "standard"
        aliases = ", ".join(f"'{a}'" for a in char.aliases) if char.aliases else "none"

        print(f"\n🎭 {char.name:<25} {role_tag}")
        print(f"   • Voice:     {char.voice_id} ({char.gender}, {char.age_group})")
        print(f"   • Traits:    {traits}")
        print(f"   • Aliases:   {aliases}")
        if char.voice_rationale:
            print(f"   • Casting:   {char.voice_rationale}")
    cast_sheet.save_json(out_path)
    print("\n" + "=" * 65)
    print(f"💾 Cast Sheet saved to: {out_path.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    main()
