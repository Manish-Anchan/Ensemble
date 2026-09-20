import os
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
    ) -> tuple[Screenplay, AudioSegment, CastSheet]:
        """
        Processes a single scene chunk end-to-end:
        1. Directs prose into structured screenplay (with JIT dynamic casting if needed)
        2. Synthesizes lines with real-time stream yielding and optional live playback
        Returns (screenplay, audio_segment, updated_cast_sheet).
        """
        # Step 1: Direct screenplay
        screenplay, updated_cast = self.director.direct_scene(
            scene=scene,
            cast_sheet=cast_sheet,
            chapter_index=scene.chapter_index,
            scene_index=scene.scene_index,
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
        scene_transition_pause = AudioSegment.silent(duration=1000) # 1s pause between dramatic scenes
        current_cast = cast_sheet
        total_scenes = len(scenes_to_run)

        for s_idx, scene in enumerate(scenes_to_run, 1):
            if on_scene_start:
                on_scene_start(scene, s_idx, total_scenes)

            t0 = time.time()
            screenplay, scene_audio, current_cast = self.produce_scene(
                scene=scene,
                cast_sheet=current_cast,
                book_title=book_title,
                on_line_stream=on_line_stream,
            )
            dur = time.time() - t0

            # Optionally cache individual scene audio
            if output_dir:
                scene_file = output_dir / f"ch{chapter.index}_scene{scene.scene_index}.wav"
                self.synthesizer.export_audio(scene_audio, scene_file)

            combined_chapter_audio += scene_audio
            if s_idx < total_scenes:
                combined_chapter_audio += scene_transition_pause

            if on_scene_done:
                on_scene_done(scene, screenplay, scene_audio, dur)

        return combined_chapter_audio, current_cast
