import io
import queue
import shutil
import subprocess
import threading
import time
from typing import Optional, Callable, Any
from pydub import AudioSegment

from ensemble.director.models import ScreenplayLine


def play_audio_segment(segment: AudioSegment) -> None:
    """
    Plays an in-memory pydub AudioSegment directly to the system speakers
    using the best available native Linux audio player (aplay, paplay, or ffplay).
    """
    wav_bytes = io.BytesIO()
    segment.export(wav_bytes, format="wav")
    raw_wav = wav_bytes.getvalue()

    # 1. Prefer ALSA aplay (native, instant, zero overhead)
    if shutil.which("aplay"):
        try:
            proc = subprocess.Popen(
                ["aplay", "-q", "-t", "wav"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.communicate(input=raw_wav)
            return
        except Exception:
            pass

    # 2. PulseAudio paplay
    if shutil.which("paplay"):
        try:
            proc = subprocess.Popen(
                ["paplay"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.communicate(input=raw_wav)
            return
        except Exception:
            pass

    # 3. Fallback to ffplay
    if shutil.which("ffplay"):
        try:
            proc = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.communicate(input=raw_wav)
            return
        except Exception:
            pass


class StreamItem:
    """Represents a single queued playable item."""
    def __init__(
        self,
        line_idx: int,
        total_lines: int,
        line: ScreenplayLine,
        voice_id: str,
        audio: AudioSegment,
    ):
        self.line_idx = line_idx
        self.total_lines = total_lines
        self.line = line
        self.voice_id = voice_id
        self.audio = audio


class PauseItem:
    """Represents a silence pause between scenes."""
    def __init__(self, duration_ms: int):
        self.duration_ms = duration_ms


class StreamPlayer:
    """
    Threaded real-time streaming audio player with jitter buffer.
    Decouples line synthesis from audio playback using a producer-consumer queue.
    Eliminates silence gaps between lines while maintaining fast start latency.
    """

    def __init__(
        self,
        min_buffer_lines: int = 2,
        min_buffer_sec: float = 4.0,
        on_line_play: Optional[Callable[[int, int, ScreenplayLine, str, float], None]] = None,
    ):
        self.min_buffer_lines = min_buffer_lines
        self.min_buffer_sec = min_buffer_sec
        self.on_line_play = on_line_play

        self.queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._playback_thread: Optional[threading.Thread] = None
        self._active_proc: Optional[subprocess.Popen] = None
        self._proc_lock = threading.Lock()
        self._is_running = False

    def start(self) -> "StreamPlayer":
        """Starts the consumer playback thread."""
        if not self._is_running:
            self._is_running = True
            self._stop_event.clear()
            self._playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
            self._playback_thread.start()
        return self

    def enqueue(
        self,
        line_idx: int,
        total_lines: int,
        line: ScreenplayLine,
        voice_id: str,
        audio: AudioSegment,
    ) -> None:
        """Pushes a synthesized line to the playback queue."""
        self.queue.put(StreamItem(line_idx, total_lines, line, voice_id, audio))

    def enqueue_pause(self, duration_ms: int = 1000) -> None:
        """Pushes a scene transition pause to the playback queue."""
        self.queue.put(PauseItem(duration_ms))

    def finish(self) -> None:
        """Notifies the player that synthesis has completed (pushes EOF sentinel)."""
        self.queue.put(None)

    def wait_until_done(self) -> None:
        """Blocks until all enqueued lines have finished playing."""
        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join()

    def stop(self) -> None:
        """Immediately interrupts playback and stops the background thread."""
        self._stop_event.set()
        with self._proc_lock:
            if self._active_proc and self._active_proc.poll() is None:
                try:
                    self._active_proc.terminate()
                except Exception:
                    pass
        # Drain remaining queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
        self.queue.put(None)
        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=1.0)
        self._is_running = False

    def _play_segment(self, segment: AudioSegment) -> None:
        """Plays an audio segment via subprocess with instant cancellation support."""
        if self._stop_event.is_set():
            return

        wav_bytes = io.BytesIO()
        segment.export(wav_bytes, format="wav")
        raw_wav = wav_bytes.getvalue()

        cmd = None
        if shutil.which("aplay"):
            cmd = ["aplay", "-q", "-t", "wav"]
        elif shutil.which("paplay"):
            cmd = ["paplay"]
        elif shutil.which("ffplay"):
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-"]

        if not cmd:
            return

        with self._proc_lock:
            if self._stop_event.is_set():
                return
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._active_proc = proc

        try:
            proc.communicate(input=raw_wav)
        except Exception:
            pass
        finally:
            with self._proc_lock:
                self._active_proc = None

    def _playback_worker(self) -> None:
        """Consumer worker loop: buffers jitter buffer, then streams lines seamlessly."""
        buffer: list[Any] = []
        buffered_duration_ms = 0

        # Phase 1: Pre-buffering jitter buffer
        while not self._stop_event.is_set():
            try:
                item = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if item is None:
                # End-of-stream reached before full buffer (e.g. short 1-line scene)
                break

            if isinstance(item, StreamItem):
                buffer.append(item)
                buffered_duration_ms += len(item.audio)
                dur_s = buffered_duration_ms / 1000.0
                count = len(buffer)
                print(f"   ⏳ [Jitter Buffer: {count}/{self.min_buffer_lines} lines ({dur_s:.1f}s audio ready)]...", flush=True)

                if count >= self.min_buffer_lines or dur_s >= self.min_buffer_sec:
                    print(f"   ▶️  Buffer threshold met ({dur_s:.1f}s ready). Starting real-time audio playback!\n", flush=True)
                    break
            elif isinstance(item, PauseItem):
                buffer.append(item)

        # Flush initial buffer items into playback
        for buffered_item in buffer:
            if self._stop_event.is_set():
                return
            self._dispatch_item(buffered_item)

        # If we broke out due to EOF sentinel in Phase 1
        if item is None:
            return

        # Phase 2: Steady-state continuous playback
        while not self._stop_event.is_set():
            try:
                item = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if item is None:
                # Normal end-of-stream
                break

            self._dispatch_item(item)

    def _dispatch_item(self, item: Any) -> None:
        """Dispatches an individual queue item for playback."""
        if isinstance(item, StreamItem):
            dur_s = len(item.audio) / 1000.0
            role = item.line.speaker.upper()

            if self.on_line_play:
                self.on_line_play(item.line_idx, item.total_lines, item.line, item.voice_id, dur_s)
            else:
                print(
                    f"   🎙️ [{item.line_idx:02d}/{item.total_lines}] 🎭 {role:<14} "
                    f"({item.voice_id} | {item.line.emotion} | {dur_s:.1f}s): \"{item.line.text}\"",
                    flush=True,
                )

            self._play_segment(item.audio)

        elif isinstance(item, PauseItem):
            pause_sec = item.duration_ms / 1000.0
            time.sleep(pause_sec)
