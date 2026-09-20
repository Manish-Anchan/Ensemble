import pytest
import numpy as np
from pathlib import Path
from pydub import AudioSegment

from ensemble.director.models import ScreenplayLine, Screenplay
from ensemble.producer.models import CastSheet, CharacterProfile
from ensemble.audio.synthesizer import DramaSynthesizer


def test_synthesizer_mock_scene(monkeypatch, tmp_path: Path):
    """Verifies that DramaSynthesizer converts screenplay lines into stitched audio with proper pauses."""
    synth = DramaSynthesizer(
        model_path="models/kokoro-v1.0.onnx",
        voices_path="models/voices-v1.0.bin",
    )

    # Mock Kokoro engine
    sample_rate = 24000
    mock_audio_samples = np.zeros(sample_rate // 2, dtype=np.float32) # 0.5 sec audio

    class MockKokoro:
        def create(self, text, voice="bm_george", speed=1.0, lang="en-us"):
            return mock_audio_samples, sample_rate

    monkeypatch.setattr(synth, "_get_engine", lambda: MockKokoro())

    screenplay = Screenplay(
        chapter_index=1,
        scene_index=1,
        lines=[
            ScreenplayLine(speaker="narrator", text="The night was cold.", emotion="solemn", speed=0.95, pause_after_ms=300),
            ScreenplayLine(speaker="char_daisy", text="I'm so happy to see you.", emotion="flirtatious", speed=1.05, pause_after_ms=400),
        ]
    )

    cast_sheet = CastSheet(
        book_title="The Great Gatsby",
        characters={
            "narrator": CharacterProfile(id="narrator", name="Nick", gender="male", age_group="adult", role="narrator", personality_traits=[], aliases=[], voice_id="am_michael"),
            "char_daisy": CharacterProfile(id="char_daisy", name="Daisy", gender="female", age_group="adult", role="supporting", personality_traits=[], aliases=[], voice_id="af_bella"),
        }
    )

    visited_lines = []
    def on_line(idx, total, line, voice_id):
        visited_lines.append((idx, line.speaker, voice_id))

    audio = synth.synthesize_scene(screenplay, cast_sheet, on_line_done=on_line)

    # 2 lines * 500ms audio + 300ms pause + 400ms pause = 1700ms total
    assert len(audio) >= 1650
    assert len(visited_lines) == 2
    assert visited_lines[0] == (1, "narrator", "am_michael")
    assert visited_lines[1] == (2, "char_daisy", "af_bella")

    # Verify export
    out_file = tmp_path / "test_scene.wav"
    exported = synth.export_audio(audio, out_file)
    assert exported.exists()
    assert exported.stat().st_size > 1000
