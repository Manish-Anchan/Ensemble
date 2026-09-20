import argparse
import sys
import time
from pathlib import Path

from ensemble.parser.extractor import load_book
from ensemble.producer.models import CastSheet, CharacterProfile
from ensemble.producer.casting import CastingProducer
from ensemble.director.director import SceneDirector
from ensemble.audio.synthesizer import DramaSynthesizer
from ensemble.drama.pipeline import DramaPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Ensemble Drama Engine: Autonomous Multi-Cast Fiction Audiobook Production"
    )
    parser.add_argument("file", help="Path to PDF or EPUB book file")
    parser.add_argument(
        "--chapter",
        type=int,
        default=1,
        help="Chapter number to produce (1-indexed, default: 1)",
    )
    parser.add_argument(
        "--scenes",
        type=int,
        default=0,
        help="Max scenes to produce in the chapter (default: 0 = all scenes)",
    )
    parser.add_argument(
        "--cast",
        type=str,
        default=None,
        help="Path to existing cast_sheet.json (default: auto-detects or creates <book_stem>_cast.json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to output master audio WAV file (default: outputs/<book_stem>_ch<chapter>.wav)",
    )
    parser.add_argument(
        "--footer-margin",
        type=float,
        default=75.0,
        help="Bottom margin (points) for PDF layout clipping (default: 75.0)",
    )
    parser.add_argument(
        "--script-only",
        action="store_true",
        help="Only run Scene Director and output screenplays without audio synthesis",
    )
    parser.add_argument(
        "--play",
        "--stream",
        action="store_true",
        dest="play",
        help="Stream audio lines live to speakers in real-time as each line is synthesized",
    )

    args = parser.parse_args()
    path = Path(args.file)
    if not path.exists():
        print(f"❌ Error: File not found: {path}")
        sys.exit(1)

    print("=" * 70)
    print("🎭 ENSEMBLE: Autonomous Multi-Cast Audio Drama Engine")
    print("=" * 70)
    print(f"Loading '{path.name}'...")

    try:
        book = load_book(path, footer_margin_pt=args.footer_margin)
    except Exception as e:
        print(f"❌ Book loading error: {e}")
        sys.exit(1)

    if not book.chapters:
        print("❌ Error: No chapters detected in book.")
        sys.exit(1)

    ch_idx = args.chapter - 1
    if ch_idx < 0 or ch_idx >= len(book.chapters):
        print(f"❌ Error: Chapter {args.chapter} does not exist (book has {len(book.chapters)} chapters).")
        sys.exit(1)

    target_chapter = book.chapters[ch_idx]

    # Load or initialize Cast Sheet
    cast_path = Path(args.cast) if args.cast else path.with_name(f"{path.stem}_cast.json")
    if cast_path.exists():
        print(f"📋 Loaded Master Cast Sheet: '{cast_path.name}'")
        cast_sheet = CastSheet.load_json(cast_path)
    else:
        print(f"📋 No Cast Sheet found. Initializing new Cast Sheet for '{book.title}'...")
        cast_sheet = CastSheet(book_title=book.title, characters={
            "narrator": CharacterProfile(
                id="narrator",
                name="Narrator",
                gender="male",
                age_group="adult",
                role="narrator",
                personality_traits=["observant", "measured"],
                aliases=["narrator"],
                voice_id="bm_george",
                voice_rationale="Default classic British fiction narrator."
            )
        })

    scenes_to_run = target_chapter.scenes
    if args.scenes and args.scenes > 0:
        scenes_to_run = target_chapter.scenes[:args.scenes]

    print(f"📖 Book: '{book.title}' by {book.author}")
    print(f"🎬 Producing '{target_chapter.title}' ({len(scenes_to_run)} scene(s), {target_chapter.word_count:,} words total)...")
    print("=" * 70)

    # Initialize pipeline
    pipeline = DramaPipeline()

    if args.script_only:
        import json
        print(f"🎬 Running Scene Director in script-only mode ({len(scenes_to_run)} scene(s))...\n")
        all_screenplays = []
        for s_idx, scene in enumerate(scenes_to_run, 1):
            t0 = time.time()
            screenplay, cast_sheet = pipeline.director.direct_scene(
                scene=scene,
                cast_sheet=cast_sheet,
                chapter_index=scene.chapter_index,
                scene_index=scene.scene_index,
            )
            dur = time.time() - t0
            all_screenplays.append(screenplay.to_dict())

            print("=" * 65)
            print(f"🎬 Scene {scene.scene_index} Screenplay ({len(screenplay.lines)} lines, {dur:.2f}s):")
            print("=" * 65)
            for i, line in enumerate(screenplay.lines, 1):
                voice = cast_sheet.get_voice_for_speaker(line.speaker)
                print(f"[{i:02d}] 🎭 {line.speaker.upper():<15} ({voice} | {line.emotion} | speed={line.speed:.2f}x)")
                print(f"     \"{line.text}\"\n")

        out_dir = Path("outputs")
        out_dir.mkdir(parents=True, exist_ok=True)
        script_file = out_dir / f"{path.stem}_ch{args.chapter}_screenplay.json"
        script_file.write_text(json.dumps(all_screenplays, indent=2), encoding="utf-8")
        cast_sheet.save_json(cast_path)
        print("=" * 65)
        print(f"💾 Full Screenplay saved to: {script_file.resolve()}")
        print("=" * 65)
        return

    player = None
    on_line_stream = None
    if args.play:
        from ensemble.audio.player import StreamPlayer
        print("🔊 Real-Time Live Playback: ENABLED (streaming lines directly to speakers via Jitter Buffer)\n")
        player = StreamPlayer(min_buffer_lines=2, min_buffer_sec=4.0)
        player.start()
        on_line_stream = player.enqueue

    def on_scene_start(scene, current_idx, total):
        print(f"\n🎬 [Scene {current_idx}/{total}] (Scene {scene.scene_index} • {scene.word_count} words)...")

    def on_scene_done(scene, screenplay, audio, duration):
        audio_dur_sec = len(audio) / 1000.0
        speakers_summary = ", ".join(f"{s} ({c})" for s, c in screenplay.speaker_counts.items())
        print(f"   ✓ Synthesized {len(screenplay.lines)} lines ({audio_dur_sec:.1f}s audio) in {duration:.2f}s [Cast: {speakers_summary}]")
        if player:
            player.enqueue_pause(1000)

    t_start = time.time()
    try:
        chapter_audio, final_cast = pipeline.produce_chapter(
            chapter=target_chapter,
            cast_sheet=cast_sheet,
            book_title=book.title,
            max_scenes=args.scenes,
            on_scene_start=on_scene_start,
            on_line_stream=on_line_stream,
            on_scene_done=on_scene_done,
        )
        if player:
            print("\n⏳ Synthesis complete. Playing out remaining queued audio...")
            player.finish()
            player.wait_until_done()
    except KeyboardInterrupt:
        print("\n\n🛑 Playback stopped by user.")
        if player:
            player.stop()
        sys.exit(0)
    except Exception as e:
        if player:
            player.stop()
        print(f"\n❌ Drama pipeline error: {e}")
        sys.exit(1)

    total_time = time.time() - t_start
    total_audio_sec = len(chapter_audio) / 1000.0

    # Save updated cast sheet if dynamic characters were discovered
    final_cast.save_json(cast_path)

    # Output master audio
    out_dir = Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = Path(args.output) if args.output else out_dir / f"{path.stem}_ch{args.chapter}.wav"
    pipeline.synthesizer.export_audio(chapter_audio, out_file)

    print("\n" + "=" * 70)
    print("✨ AUDIO DRAMA PRODUCTION COMPLETE!")
    print("=" * 70)
    print(f"⏱️  Production Time:  {total_time:.2f}s")
    print(f"🎧  Audio Duration:   {total_audio_sec:.1f}s ({total_audio_sec/60:.2f} minutes)")
    print(f"⚡  Synthesis Speed:  {total_audio_sec / max(total_time, 0.001):.1f}x real-time")
    print(f"💾  Master Audio:     {out_file.resolve()}")
    print(f"📋  Saved Cast Sheet: {cast_path.resolve()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
