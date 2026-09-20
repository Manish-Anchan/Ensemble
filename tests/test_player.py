import time
import pytest
from pydub import AudioSegment

from ensemble.director.models import ScreenplayLine
from ensemble.audio.player import StreamPlayer, StreamItem, PauseItem


def test_stream_player_buffering_and_playback(monkeypatch):
    """Verifies StreamPlayer buffers before playing and consumes queue items in order."""
    played_lines = []

    player = StreamPlayer(
        min_buffer_lines=2,
        min_buffer_sec=0.2,
        on_line_play=lambda idx, total, line, voice, dur: played_lines.append((idx, line.speaker, voice)),
    )

    # Mock audio subprocess playback to avoid actual sound card usage in unit tests
    monkeypatch.setattr(player, "_play_segment", lambda seg: time.sleep(0.01))

    player.start()

    line1 = ScreenplayLine(speaker="narrator", text="First line", emotion="neutral")
    line2 = ScreenplayLine(speaker="daisy", text="Second line", emotion="excited")
    line3 = ScreenplayLine(speaker="tom", text="Third line", emotion="angry")

    # 100ms silent audio
    silence = AudioSegment.silent(duration=100)

    player.enqueue(1, 3, line1, "bm_george", silence)
    player.enqueue(2, 3, line2, "af_bella", silence)
    player.enqueue(3, 3, line3, "am_michael", silence)
    player.enqueue_pause(50)
    player.finish()

    player.wait_until_done()

    assert len(played_lines) == 3
    assert played_lines[0] == (1, "narrator", "bm_george")
    assert played_lines[1] == (2, "daisy", "af_bella")
    assert played_lines[2] == (3, "tom", "am_michael")


def test_stream_player_instant_stop(monkeypatch):
    """Verifies that player.stop() drains remaining queue and exits cleanly."""
    player = StreamPlayer(min_buffer_lines=1)
    monkeypatch.setattr(player, "_play_segment", lambda seg: time.sleep(0.5))

    player.start()
    line = ScreenplayLine(speaker="narrator", text="Test line", emotion="neutral")
    silence = AudioSegment.silent(duration=100)

    player.enqueue(1, 10, line, "bm_george", silence)
    time.sleep(0.05)
    player.stop()

    assert player._stop_event.is_set()
    assert not player._is_running
