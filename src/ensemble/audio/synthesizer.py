import os
import io
import time
from typing import Optional, Callable, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
import numpy as np
import soundfile as sf
from pydub import AudioSegment
from kokoro_onnx import Kokoro

from ensemble.director.models import ScreenplayLine, Screenplay
from ensemble.producer.models import CastSheet

load_dotenv()


class DramaSynthesizer:
    """
    Multi-Cast Audio Drama Synthesizer.
    Converts structured Screenplay lines into expressive multi-speaker audio
    using Kokoro-82M ONNX and stitches with dynamic natural pauses.
    """

    def __init__(
        self,
        model_path: Optional[str | Path] = None,
        voices_path: Optional[str | Path] = None,
    ):
        self.model_path = Path(model_path or os.getenv("KOKORO_MODEL_PATH", "models/kokoro-v1.0.onnx"))
        self.voices_path = Path(voices_path or os.getenv("KOKORO_VOICES_PATH", "models/voices-v1.0.bin"))
        self._kokoro: Optional[Kokoro] = None

    def _get_engine(self) -> Kokoro:
        """Lazy loader for Kokoro-82M ONNX model."""
        if self._kokoro is None:
            if not self.model_path.exists():
                raise FileNotFoundError(f"Kokoro model not found at: {self.model_path.resolve()}")
            if not self.voices_path.exists():
                raise FileNotFoundError(f"Kokoro voices file not found at: {self.voices_path.resolve()}")

            self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))
        return self._kokoro

    def synthesize_line(
        self,
        text: str,
        voice_id: str = "bm_george",
        speed: float = 1.0,
        lang: str = "en-us",
    ) -> AudioSegment:
        """
        Synthesizes a single line of text into a pydub AudioSegment.
        """
        engine = self._get_engine()
        samples, sr = engine.create(text, voice=voice_id, speed=speed, lang=lang)

        # Fast conversion from float32 numpy array to 16-bit PCM AudioSegment
        pcm16 = (samples * 32767.0).clip(-32768, 32767).astype(np.int16)
        return AudioSegment(pcm16.tobytes(), frame_rate=sr, sample_width=2, channels=1)

    def stream_scene_lines(
        self,
        screenplay: Screenplay,
        cast_sheet: CastSheet,
    ):
        """
        Yields each synthesized line as soon as it is generated for real-time streaming.
        Yields: (line_index, total_lines, ScreenplayLine, voice_id, AudioSegment)
        """
        total_lines = len(screenplay.lines)
        for i, line in enumerate(screenplay.lines, 1):
            text = line.text.strip()
            if not text:
                continue

            voice_id = cast_sheet.get_voice_for_speaker(line.speaker)
            lang = "en-gb" if voice_id.startswith("b") else "en-us"

            # Apply speed from line, modulated by emotion
            speed = line.speed
            emotion_lower = line.emotion.lower()
            if emotion_lower in ("urgent", "panic", "shout", "excited"):
                speed = max(speed, 1.08)
            elif emotion_lower in ("whisper", "grim", "solemn", "mournful", "wistful"):
                speed = min(speed, 0.94)

            # Synthesize audio segment
            line_audio = self.synthesize_line(text, voice_id=voice_id, speed=speed, lang=lang)

            # Append dynamic pause
            if line.pause_after_ms > 0:
                line_audio += AudioSegment.silent(duration=line.pause_after_ms)

            yield i, total_lines, line, voice_id, line_audio

    def synthesize_scene(
        self,
        screenplay: Screenplay,
        cast_sheet: CastSheet,
        on_line_done: Optional[Callable[[int, int, ScreenplayLine, str], None]] = None,
    ) -> AudioSegment:
        """
        Synthesizes an entire Screenplay scene with multi-cast voices and natural pauses.
        Returns a combined AudioSegment.
        """
        combined = AudioSegment.empty()
        for i, total_lines, line, voice_id, line_audio in self.stream_scene_lines(screenplay, cast_sheet):
            combined += line_audio
            if on_line_done:
                on_line_done(i, total_lines, line, voice_id)

        return combined

    @staticmethod
    def export_audio(
        audio: AudioSegment,
        output_path: str | Path,
        format: str = "wav",
    ) -> Path:
        """Exports an AudioSegment to disk."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        audio.export(str(out), format=format)
        return out
