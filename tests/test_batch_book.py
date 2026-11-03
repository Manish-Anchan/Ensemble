import json
import pytest
from pathlib import Path
from pydub import AudioSegment

from ensemble.parser.models import Book, Chapter, SceneChunk
from ensemble.producer.models import CastSheet, CharacterProfile
from ensemble.director.models import Screenplay, ScreenplayLine
from ensemble.director.director import SceneDirector
from ensemble.drama.pipeline import DramaPipeline


@pytest.fixture
def mock_book():
    """Builds a lightweight 2-chapter mock Book."""
    ch1 = Chapter(
        index=1,
        title="Chapter 1",
        raw_text="The night was still.",
        clean_text="The night was still.",
        page_start=1,
        page_end=2,
        scenes=[
            SceneChunk(chapter_index=1, scene_index=1, text="The night was still.", word_count=4, start_paragraph=0, end_paragraph=1),
        ]
    )
    ch2 = Chapter(
        index=2,
        title="Chapter 2",
        raw_text="The morning came quickly.",
        clean_text="The morning came quickly.",
        page_start=3,
        page_end=4,
        scenes=[
            SceneChunk(chapter_index=2, scene_index=1, text="The morning came quickly.", word_count=4, start_paragraph=0, end_paragraph=1),
        ]
    )
    return Book(
        title="Mock Book",
        author="Mock Author",
        chapters=[ch1, ch2]
    )


@pytest.fixture
def mock_cast():
    return CastSheet(
        book_title="Mock Book",
        characters={
            "narrator": CharacterProfile(
                id="narrator", name="Narrator", gender="male", age_group="adult",
                role="narrator", personality_traits=[], aliases=[], voice_id="bm_george"
            )
        }
    )


def test_produce_book_batch(monkeypatch, tmp_path: Path, mock_book, mock_cast):
    """Verifies that produce_book processes chapters, exports files, and generates a manifest."""
    pipeline = DramaPipeline(director=SceneDirector(api_key="mock-key"))

    # Mock director to avoid external API calls
    def mock_direct(scene, cast_sheet=None, chapter_index=1, scene_index=1, **kwargs):
        sp = Screenplay(
            chapter_index=chapter_index,
            scene_index=scene_index,
            lines=[
                ScreenplayLine(speaker="narrator", text=scene.text, emotion="neutral", speed=1.0, pause_after_ms=100)
            ]
        )
        return sp, cast_sheet

    # Mock synthesize_line to avoid ONNX model download
    silence = AudioSegment.silent(duration=500)
    monkeypatch.setattr(pipeline.director, "direct_scene", mock_direct)
    monkeypatch.setattr(pipeline.synthesizer, "synthesize_line", lambda text, voice_id, speed, lang: silence)

    out_dir = tmp_path / "mock_book_output"

    started_chapters = []
    done_chapters = []

    def on_ch_start(ch, idx, total):
        started_chapters.append(ch.index)

    def on_ch_done(ch, out_file, dur, elapsed, skipped):
        done_chapters.append((ch.index, skipped))

    chapter_files, final_cast, manifest = pipeline.produce_book(
        book=mock_book,
        cast_sheet=mock_cast,
        output_dir=out_dir,
        resume=True,
        on_chapter_start=on_ch_start,
        on_chapter_done=on_ch_done,
    )

    assert len(chapter_files) == 2
    assert (out_dir / "Chapter_01.wav").exists()
    assert (out_dir / "Chapter_02.wav").exists()
    assert (out_dir / "Chapter_01_screenplay.json").exists()
    assert (out_dir / "Chapter_02_screenplay.json").exists()
    assert (out_dir / "production_manifest.json").exists()
    assert (out_dir / "cast_sheet.json").exists()

    assert started_chapters == [1, 2]
    assert done_chapters == [(1, False), (2, False)]

    manifest_data = json.loads((out_dir / "production_manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["book_title"] == "Mock Book"
    assert len(manifest_data["chapters"]) == 2


def test_produce_book_resume_skips_existing(monkeypatch, tmp_path: Path, mock_book, mock_cast):
    """Verifies that produce_book with resume=True skips already produced chapter files."""
    pipeline = DramaPipeline(director=SceneDirector(api_key="mock-key"))

    def mock_direct(scene, cast_sheet=None, chapter_index=1, scene_index=1, **kwargs):
        return Screenplay(chapter_index=chapter_index, scene_index=scene_index, lines=[]), cast_sheet

    silence = AudioSegment.silent(duration=500)
    monkeypatch.setattr(pipeline.director, "direct_scene", mock_direct)
    monkeypatch.setattr(pipeline.synthesizer, "synthesize_line", lambda text, voice_id, speed, lang: silence)

    out_dir = tmp_path / "mock_book_resume"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pre-create Chapter 1 audio (>1000 bytes)
    ch1_file = out_dir / "Chapter_01.wav"
    silence.export(str(ch1_file), format="wav")
    assert ch1_file.stat().st_size > 1000

    done_chapters = []

    def on_ch_done(ch, out_file, dur, elapsed, skipped):
        done_chapters.append((ch.index, skipped))

    chapter_files, final_cast, manifest = pipeline.produce_book(
        book=mock_book,
        cast_sheet=mock_cast,
        output_dir=out_dir,
        resume=True,
        on_chapter_done=on_ch_done,
    )

    # Chapter 1 should have skipped=True, Chapter 2 skipped=False
    assert done_chapters == [(1, True), (2, False)]
    assert (out_dir / "Chapter_02.wav").exists()
