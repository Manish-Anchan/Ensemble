import os
import json
import time
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
from pydub import AudioSegment

from ensemble.parser.models import Book, Chapter, SceneChunk
from ensemble.producer.models import CastSheet
from ensemble.producer.casting import CastingProducer
from ensemble.director.models import Screenplay, ScreenplayLine
from ensemble.director.director import SceneDirector
from ensemble.audio.synthesizer import DramaSynthesizer


class DramaPipeline:
    """
    End-to-end Audio Drama Production Pipeline.
    Wires Book Ingestion -> Cast Sheet -> Scene Director -> Kokoro Synthesis.
    Supports single scenes, full chapters, and multi-chapter book batch production with resume support.
    """

    def __init__(
        self,
        director: Optional[SceneDirector] = None,
        synthesizer: Optional[DramaSynthesizer] = None,
        producer: Optional[CastingProducer] = None,
    ):
        self.director = director or SceneDirector()
        self.synthesizer = synthesizer or DramaSynthesizer()
        self.producer = producer or CastingProducer()

    def produce_scene(
        self,
        scene: SceneChunk,
        cast_sheet: CastSheet,
        book_title: str,
        on_line_stream: Optional[Callable[[int, int, ScreenplayLine, str, AudioSegment], None]] = None,
        previous_scene_context: Optional[str] = None,
    ) -> tuple[Screenplay, AudioSegment, CastSheet]:
        """
        Processes a single scene chunk end-to-end:
        1. Directs prose into structured screenplay (with JIT dynamic casting if needed)
        2. Synthesizes lines with real-time stream yielding and optional live playback
        Returns (screenplay, audio_segment, updated_cast_sheet).
        """
        # Step 1: Direct screenplay
        kwargs = {}
        if previous_scene_context:
            kwargs["previous_scene_context"] = previous_scene_context

        screenplay, updated_cast = self.director.direct_scene(
            scene=scene,
            cast_sheet=cast_sheet,
            chapter_index=scene.chapter_index,
            scene_index=scene.scene_index,
            **kwargs,
        )
        current_cast = updated_cast or cast_sheet

        # Step 2: Synthesize audio lines
        combined = AudioSegment.empty()
        for i, total_lines, line, voice_id, line_audio in self.synthesizer.stream_scene_lines(screenplay, current_cast):
            combined += line_audio
            if on_line_stream:
                on_line_stream(i, total_lines, line, voice_id, line_audio)

        return screenplay, combined, current_cast

    def produce_chapter(
        self,
        chapter: Chapter,
        cast_sheet: CastSheet,
        book_title: str,
        max_scenes: Optional[int] = None,
        output_dir: Optional[Path] = None,
        audio_format: str = "wav",
        on_scene_start: Optional[Callable[[SceneChunk, int, int], None]] = None,
        on_line_stream: Optional[Callable[[int, int, ScreenplayLine, str, AudioSegment], None]] = None,
        on_scene_done: Optional[Callable[[SceneChunk, Screenplay, AudioSegment, float], None]] = None,
    ) -> tuple[AudioSegment, CastSheet]:
        """
        Produces an entire chapter scene-by-scene, concatenating audio into a master chapter track.
        """
        scenes_to_run = chapter.scenes
        if max_scenes and max_scenes > 0:
            scenes_to_run = chapter.scenes[:max_scenes]

        combined_chapter_audio = AudioSegment.empty()
        scene_transition_pause = AudioSegment.silent(duration=1000)  # 1s pause between dramatic scenes
        current_cast = cast_sheet
        total_scenes = len(scenes_to_run)
        fmt = "mp3" if audio_format.lower() == "mp3" else "wav"

        last_scene_text: Optional[str] = None
        last_active_speakers: List[str] = []

        for s_idx, scene in enumerate(scenes_to_run, 1):
            if on_scene_start:
                on_scene_start(scene, s_idx, total_scenes)

            # Build rolling previous scene context for pronoun and character continuity
            previous_scene_context = None
            if last_scene_text:
                words = last_scene_text.strip().split()
                trailing_words = " ".join(words[-200:]) if len(words) > 200 else last_scene_text.strip()
                speakers_hint = f"Characters active in previous scene: {', '.join(last_active_speakers)}\n" if last_active_speakers else ""
                previous_scene_context = f"{speakers_hint}Ending of previous scene:\n\"{trailing_words}\""
            elif scene.scene_index > 1:
                # Direct jump to scene N > 1; fetch preceding scene from full chapter if available
                prev_scene_obj = next((s for s in chapter.scenes if s.scene_index == scene.scene_index - 1), None)
                if prev_scene_obj and prev_scene_obj.text:
                    words = prev_scene_obj.text.strip().split()
                    trailing_words = " ".join(words[-200:]) if len(words) > 200 else prev_scene_obj.text.strip()
                    previous_scene_context = f"Ending of preceding scene:\n\"{trailing_words}\""

            t0 = time.time()
            screenplay, scene_audio, current_cast = self.produce_scene(
                scene=scene,
                cast_sheet=current_cast,
                book_title=book_title,
                on_line_stream=on_line_stream,
                previous_scene_context=previous_scene_context,
            )
            dur = time.time() - t0

            last_scene_text = scene.text
            last_active_speakers = [
                current_cast.characters[spk].name for spk in screenplay.speaker_counts.keys()
                if spk in current_cast.characters and spk != "narrator"
            ]

            # Optionally cache individual scene audio
            if output_dir:
                scene_file = output_dir / f"ch{chapter.index}_scene{scene.scene_index}.{fmt}"
                self.synthesizer.export_audio(scene_audio, scene_file, format=fmt)

            combined_chapter_audio += scene_audio
            if s_idx < total_scenes:
                combined_chapter_audio += scene_transition_pause

            if on_scene_done:
                on_scene_done(scene, screenplay, scene_audio, dur)

        return combined_chapter_audio, current_cast

    def produce_book(
        self,
        book: Book,
        cast_sheet: CastSheet,
        output_dir: Path | str,
        resume: bool = True,
        start_chapter: int = 1,
        end_chapter: Optional[int] = None,
        max_scenes_per_chapter: Optional[int] = None,
        script_only: bool = False,
        audio_format: str = "wav",
        on_chapter_start: Optional[Callable[[Chapter, int, int], None]] = None,
        on_chapter_done: Optional[Callable[[Chapter, Path, float, float, bool], None]] = None,
        on_scene_start: Optional[Callable[[SceneChunk, int, int], None]] = None,
        on_line_stream: Optional[Callable[[int, int, ScreenplayLine, str, AudioSegment], None]] = None,
        on_scene_done: Optional[Callable[[SceneChunk, Screenplay, AudioSegment, float], None]] = None,
    ) -> tuple[Dict[int, Path], CastSheet, Dict[str, Any]]:
        """
        Produces an entire novel chapter-by-chapter in batch mode.
        Saves individual chapter tracks (Chapter_01.wav or Chapter_01.mp3), screenplays, and a master production manifest.
        Supports resume mode to skip already-produced chapters.
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        fmt = "mp3" if audio_format.lower() == "mp3" else "wav"

        target_chapters = [
            ch for ch in book.chapters
            if ch.index >= start_chapter and (end_chapter is None or ch.index <= end_chapter)
        ]

        current_cast = cast_sheet
        chapter_files: Dict[int, Path] = {}
        total_targets = len(target_chapters)

        manifest: Dict[str, Any] = {
            "book_title": book.title,
            "author": book.author or "Unknown",
            "audio_format": fmt,
            "total_book_chapters": len(book.chapters),
            "target_chapters": [ch.index for ch in target_chapters],
            "chapters": [],
            "total_audio_duration_sec": 0.0,
            "total_production_time_sec": 0.0,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        for idx, chapter in enumerate(target_chapters, 1):
            ch_num = chapter.index
            chapter_audio_file = out_path / f"Chapter_{ch_num:02d}.{fmt}"
            chapter_script_file = out_path / f"Chapter_{ch_num:02d}_screenplay.json"

            # Check if this chapter was already produced when resume is enabled
            if resume and not script_only and chapter_audio_file.exists() and chapter_audio_file.stat().st_size > 1000:
                if fmt == "mp3":
                    # MP3 ~128kbps = 16,000 bytes/sec estimate
                    est_dur_sec = chapter_audio_file.stat().st_size / 16000.0
                else:
                    # Estimate audio duration from 24kHz 16-bit mono PCM (48,000 bytes/sec)
                    file_bytes = max(0, chapter_audio_file.stat().st_size - 44)
                    est_dur_sec = file_bytes / 48000.0

                chapter_files[ch_num] = chapter_audio_file
                manifest["chapters"].append({
                    "chapter_index": ch_num,
                    "title": chapter.title,
                    "file": chapter_audio_file.name,
                    "audio_duration_sec": round(est_dur_sec, 2),
                    "production_time_sec": 0.0,
                    "status": "skipped_already_exists",
                    "word_count": chapter.word_count,
                })
                manifest["total_audio_duration_sec"] += est_dur_sec

                if on_chapter_done:
                    on_chapter_done(chapter, chapter_audio_file, est_dur_sec, 0.0, True)
                continue

            if on_chapter_start:
                on_chapter_start(chapter, idx, total_targets)

            t0 = time.time()
            chapter_screenplays = []

            def collect_scene_screenplay(sc, sp, aud, dur):
                chapter_screenplays.append(sp.to_dict())
                if on_scene_done:
                    on_scene_done(sc, sp, aud, dur)

            if script_only:
                # Script-only mode: direct all scenes without Kokoro audio synthesis
                scenes_to_run = chapter.scenes
                if max_scenes_per_chapter and max_scenes_per_chapter > 0:
                    scenes_to_run = chapter.scenes[:max_scenes_per_chapter]

                for s_idx, scene in enumerate(scenes_to_run, 1):
                    if on_scene_start:
                        on_scene_start(scene, s_idx, len(scenes_to_run))
                    sp_t0 = time.time()
                    screenplay, current_cast = self.director.direct_scene(
                        scene=scene,
                        cast_sheet=current_cast,
                        chapter_index=scene.chapter_index,
                        scene_index=scene.scene_index,
                    )
                    sp_dur = time.time() - sp_t0
                    chapter_screenplays.append(screenplay.to_dict())
                    if on_scene_done:
                        on_scene_done(scene, screenplay, AudioSegment.empty(), sp_dur)

                elapsed = time.time() - t0
                with open(chapter_script_file, "w", encoding="utf-8") as sf:
                    json.dump(chapter_screenplays, sf, indent=2, ensure_ascii=False)

                chapter_files[ch_num] = chapter_script_file
                manifest["chapters"].append({
                    "chapter_index": ch_num,
                    "title": chapter.title,
                    "script_file": chapter_script_file.name,
                    "audio_duration_sec": 0.0,
                    "production_time_sec": round(elapsed, 2),
                    "status": "script_only_produced",
                    "word_count": chapter.word_count,
                })
                manifest["total_production_time_sec"] += elapsed

                if on_chapter_done:
                    on_chapter_done(chapter, chapter_script_file, 0.0, elapsed, False)

            else:
                # Full production mode: direct screenplay + synthesize Kokoro audio
                chapter_audio, current_cast = self.produce_chapter(
                    chapter=chapter,
                    cast_sheet=current_cast,
                    book_title=book.title,
                    max_scenes=max_scenes_per_chapter,
                    audio_format=fmt,
                    on_scene_start=on_scene_start,
                    on_line_stream=on_line_stream,
                    on_scene_done=collect_scene_screenplay,
                )
                elapsed = time.time() - t0
                dur_sec = len(chapter_audio) / 1000.0

                # Export chapter audio
                self.synthesizer.export_audio(chapter_audio, chapter_audio_file, format=fmt)

                # Export chapter screenplays
                if chapter_screenplays:
                    with open(chapter_script_file, "w", encoding="utf-8") as sf:
                        json.dump(chapter_screenplays, sf, indent=2, ensure_ascii=False)

                chapter_files[ch_num] = chapter_audio_file
                manifest["chapters"].append({
                    "chapter_index": ch_num,
                    "title": chapter.title,
                    "file": chapter_audio_file.name,
                    "script_file": chapter_script_file.name,
                    "audio_duration_sec": round(dur_sec, 2),
                    "production_time_sec": round(elapsed, 2),
                    "status": "produced",
                    "word_count": chapter.word_count,
                })
                manifest["total_audio_duration_sec"] += dur_sec
                manifest["total_production_time_sec"] += elapsed

                if on_chapter_done:
                    on_chapter_done(chapter, chapter_audio_file, dur_sec, elapsed, False)

            # Persist updated cast sheet after every chapter so newly discovered characters persist
            current_cast.save_json(out_path / "cast_sheet.json")

        # Save production manifest
        manifest_file = out_path / "production_manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2, ensure_ascii=False)

        return chapter_files, current_cast, manifest
