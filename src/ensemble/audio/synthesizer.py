import os
import io
import time
from typing import Optional, Callable, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
import sys
import glob
import ctypes
import onnxruntime as ort
import numpy as np
import soundfile as sf
from pydub import AudioSegment
from kokoro_onnx import Kokoro

from ensemble.director.models import ScreenplayLine, Screenplay
from ensemble.producer.models import CastSheet

load_dotenv()


def _configure_nvidia_libs():
    """Configures library paths and preloads NVIDIA CUDA/cuDNN libraries from site-packages or host."""
    nvidia_dirs = []
    # 1. Look in site-packages nvidia directories
    for p in sys.path:
        nvidia_path = Path(p) / "nvidia"
        if nvidia_path.exists():
            for lib_dir in nvidia_path.glob("*/lib"):
                if lib_dir.is_dir():
                    nvidia_dirs.append(str(lib_dir))

    # 2. Look in project models/cuda_libs directory
    project_root = Path(__file__).resolve().parents[3]
    local_cuda_libs = project_root / "models" / "cuda_libs"
    if local_cuda_libs.exists():
        nvidia_dirs.append(str(local_cuda_libs))

    # 3. Look in host CUDA directories
    ollama_dir = "/usr/local/lib/ollama"
    if os.path.exists(ollama_dir):
        nvidia_dirs.append(ollama_dir)

    if nvidia_dirs:
        curr_ld = os.environ.get("LD_LIBRARY_PATH", "")
        new_ld = ":".join(nvidia_dirs) + (":" + curr_ld if curr_ld else "")
        os.environ["LD_LIBRARY_PATH"] = new_ld

        # Preload shared objects with RTLD_GLOBAL so ONNX Runtime finds them
        for d in nvidia_dirs:
            for so_file in glob.glob(f"{d}/*.so*"):
                try:
                    ctypes.CDLL(so_file, mode=ctypes.RTLD_GLOBAL)
                except Exception:
                    pass


class DramaSynthesizer:
    """
    Multi-Cast Audio Drama Synthesizer.
    Converts structured Screenplay lines into expressive multi-speaker audio
    using Kokoro-82M ONNX with GPU (CUDA) acceleration and dynamic natural pauses.
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
        """Lazy loader for Kokoro-82M ONNX model with GPU acceleration and tuned CPU fallback."""
        if self._kokoro is None:
            if not self.model_path.exists():
                raise FileNotFoundError(f"Kokoro model not found at: {self.model_path.resolve()}")
            if not self.voices_path.exists():
                raise FileNotFoundError(f"Kokoro voices file not found at: {self.voices_path.resolve()}")

            _configure_nvidia_libs()

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = min(8, os.cpu_count() or 4)
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            available = ort.get_available_providers()
            providers = []
            if "CUDAExecutionProvider" in available:
                cuda_opts = {
                    "cudnn_conv_algo_search": "DEFAULT",
                }
                providers.append(("CUDAExecutionProvider", cuda_opts))
            providers.append("CPUExecutionProvider")

            try:
                sess = ort.InferenceSession(str(self.model_path), sess_options=opts, providers=providers)
                print(f"⚡ Kokoro ONNX active providers: {sess.get_providers()}")
                self._kokoro = Kokoro.from_session(sess, str(self.voices_path))
            except Exception as e:
                print(f"⚠️ GPU initialization failed ({e}), falling back to optimized CPU.")
                sess = ort.InferenceSession(str(self.model_path), sess_options=opts, providers=["CPUExecutionProvider"])
                self._kokoro = Kokoro.from_session(sess, str(self.voices_path))
                
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
        Gracefully handles empty strings, non-alphanumeric punctuation, or synthesis errors
        by returning silence instead of crashing the pipeline.
        """
        clean_text = text.strip() if text else ""
        if not clean_text or not any(c.isalnum() for c in clean_text):
            return AudioSegment.silent(duration=250, frame_rate=24000)

        engine = self._get_engine()
        try:
            samples, sr = engine.create(clean_text, voice=voice_id, speed=speed, lang=lang)
            # Fast conversion from float32 numpy array to 16-bit PCM AudioSegment
            pcm16 = (samples * 32767.0).clip(-32768, 32767).astype(np.int16)
            return AudioSegment(pcm16.tobytes(), frame_rate=sr, sample_width=2, channels=1)
        except Exception as e:
            print(f"⚠️ Synthesis error for text '{clean_text[:40]}...': {e}. Emitting silence fallback.")
            return AudioSegment.silent(duration=300, frame_rate=24000)

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
            if not text or not any(c.isalnum() for c in text):
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
