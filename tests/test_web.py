import pytest
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from pydub import AudioSegment

from ensemble.web.app import app
import ensemble.web.app as web_app
from ensemble.director.models import Screenplay, ScreenplayLine


@pytest.fixture
def client():
    return TestClient(app)


def test_index_page(client):
    """Verifies that the Studio UI landing page loads with valid HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "ENSEMBLE" in response.text
    assert "visualizer-canvas" in response.text
    assert "teleprompter-list" in response.text


def test_list_books(client):
    """Verifies the /api/books endpoint returns available fiction books."""
    response = client.get("/api/books")
    assert response.status_code == 200
    data = response.json()
    assert "books" in data
    filenames = [b["filename"] for b in data["books"]]
    assert "the_great_gatsby.pdf" in filenames


def test_get_book_chapters(client):
    """Verifies the /api/books/{filename}/chapters endpoint parses chapters."""
    response = client.get("/api/books/the_great_gatsby.pdf/chapters")
    assert response.status_code == 200
    data = response.json()
    assert data["total_chapters"] >= 9
    assert len(data["chapters"]) >= 9
    assert data["chapters"][0]["index"] == 1
    assert data["chapters"][0]["scene_count"] >= 1


def test_list_voices(client):
    """Verifies that the /api/voices endpoint lists all 28 Kokoro voices."""
    response = client.get("/api/voices")
    assert response.status_code == 200
    data = response.json()
    assert "voices" in data
    assert len(data["voices"]) == 26
    voice_ids = [v["voice_id"] for v in data["voices"]]
    assert "bm_george" in voice_ids
    assert "af_bella" in voice_ids
    assert "am_adam" in voice_ids


def test_get_and_update_cast(client):
    """Verifies retrieval and updating of character cast sheets."""
    response = client.get("/api/books/the_great_gatsby.pdf/cast")
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert "characters" in data
    assert "narrator" in data["characters"]

    # Test update
    payload = {
        "book_title": "The Great Gatsby",
        "narrator_id": "narrator",
        "characters": data["characters"]
    }
    update_resp = client.post("/api/books/the_great_gatsby.pdf/cast", json=payload)
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "saved"


def test_voice_sample(client, monkeypatch):
    """Verifies /api/voice-sample/{voice_id} returns WAV audio."""
    # Mock synthesizer to avoid waiting for Kokoro ONNX model synthesis
    synth = MagicMock()
    synth.synthesize_line.return_value = AudioSegment.silent(duration=500)
    monkeypatch.setattr(web_app, "get_synthesizer", lambda: synth)

    # Clear cache for testing
    web_app._voice_samples_cache.clear()

    response = client.get("/api/voice-sample/bm_george")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert len(response.content) > 44


def test_list_outputs(client):
    """Verifies /api/outputs returns generated audio tracks."""
    response = client.get("/api/outputs")
    assert response.status_code == 200
    data = response.json()
    assert "outputs" in data
    assert isinstance(data["outputs"], list)


def test_websocket_streaming_flow(client, monkeypatch):
    """Verifies real-time WebSocket drama streaming communication."""
    # Mock director to return a simple screenplay immediately
    mock_director = MagicMock()
    mock_screenplay = Screenplay(
        chapter_index=1,
        scene_index=1,
        lines=[
            ScreenplayLine(speaker="narrator", text="The green light shone across the bay.", emotion="reflective", speed=1.0, pause_after_ms=300),
            ScreenplayLine(speaker="char_daisy", text="I'm p-paralyzed with happiness.", emotion="breathless", speed=1.05, pause_after_ms=400),
        ]
    )
    mock_director.direct_scene.return_value = (mock_screenplay, None)
    monkeypatch.setattr(web_app, "get_director", lambda: mock_director)

    # Mock synthesizer to yield audio lines quickly
    mock_synth = MagicMock()
    def mock_stream(screenplay, cast_sheet):
        for i, line in enumerate(screenplay.lines, 1):
            yield i, len(screenplay.lines), line, "bm_george", AudioSegment.silent(duration=300)

    mock_synth.stream_scene_lines = mock_stream
    monkeypatch.setattr(web_app, "get_synthesizer", lambda: mock_synth)

    with client.websocket_connect("/ws/stream/the_great_gatsby.pdf") as websocket:
        websocket.send_json({"action": "start", "chapter": 1, "scenes": 1})

        # 1. Started event
        msg1 = websocket.receive_json()
        assert msg1["type"] == "started"
        assert msg1["chapter_index"] == 1

        # 2. Chapter start event
        msg_ch = websocket.receive_json()
        assert msg_ch["type"] == "chapter_start"
        assert msg_ch["chapter_index"] == 1

        # 3. Scene start event
        msg2 = websocket.receive_json()
        assert msg2["type"] == "scene_start"
        assert msg2["scene_index"] == 1

        # 4. Screenplay ready event
        msg3 = websocket.receive_json()
        assert msg3["type"] == "screenplay_ready"
        assert msg3["total_lines"] == 2
        assert len(msg3["lines"]) == 2

        # 5. Line audio events
        line1 = websocket.receive_json()
        assert line1["type"] == "line_audio"
        assert line1["line_index"] == 1
        assert "audio_base64" in line1

        line2 = websocket.receive_json()
        assert line2["type"] == "line_audio"
        assert line2["line_index"] == 2

        # 6. Scene completed
        scene_done = websocket.receive_json()
        assert scene_done["type"] == "scene_completed"

        # 7. Chapter completed
        ch_done = websocket.receive_json()
        assert ch_done["type"] == "chapter_completed"
        assert ch_done["chapter_index"] == 1

        # 8. Finished
        finished = websocket.receive_json()
        assert finished["type"] == "finished"


def test_session_isolated_books(client, tmp_path):
    """Verifies that uploaded books in one session are isolated from other sessions."""
    import shutil
    session_a = "usr_test_alpha"
    session_b = "usr_test_beta"

    # Copy a sample pdf as a mock upload for Session A
    sess_a_dir = web_app.get_session_samples_dir(session_a)
    test_pdf = sess_a_dir / "user_a_novel.pdf"
    shutil.copy(web_app.SAMPLES_DIR / "the_great_gatsby.pdf", test_pdf)

    try:
        # Session A requests books: should see user_a_novel.pdf
        resp_a = client.get("/api/books", headers={"X-Session-ID": session_a})
        assert resp_a.status_code == 200
        books_a = [b["filename"] for b in resp_a.json()["books"]]
        assert "user_a_novel.pdf" in books_a

        # Session B requests books: should NOT see user_a_novel.pdf
        resp_b = client.get("/api/books", headers={"X-Session-ID": session_b})
        assert resp_b.status_code == 200
        books_b = [b["filename"] for b in resp_b.json()["books"]]
        assert "user_a_novel.pdf" not in books_b
        # But should still see global shared sample books
        assert "the_great_gatsby.pdf" in books_b
    finally:
        shutil.rmtree(web_app.SAMPLES_DIR / "sessions" / session_a, ignore_errors=True)


def test_session_isolated_cast(client):
    """Verifies that cast sheet updates in Session A do not overwrite Session B or global cast."""
    import shutil
    session_a = "usr_test_alpha"
    session_b = "usr_test_beta"

    try:
        # Session A customizes Tom Buchanan to bm_george
        payload = {
            "book_title": "The Great Gatsby",
            "narrator_id": "narrator",
            "characters": {
                "narrator": {
                    "id": "narrator",
                    "name": "Nick",
                    "voice_id": "am_michael",
                    "gender": "male",
                    "age_group": "adult",
                    "role": "narrator",
                    "personality_traits": [],
                    "aliases": ["Nick"],
                    "voice_rationale": "",
                },
                "char_tom": {
                    "id": "char_tom",
                    "name": "Tom Buchanan",
                    "voice_id": "bm_george",  # Customized
                    "gender": "male",
                    "age_group": "adult",
                    "role": "antagonist",
                    "personality_traits": [],
                    "aliases": ["Tom"],
                    "voice_rationale": "",
                }
            }
        }
        save_resp = client.post(
            "/api/books/the_great_gatsby.pdf/cast",
            json=payload,
            headers={"X-Session-ID": session_a}
        )
        assert save_resp.status_code == 200

        # Session A should see Tom with bm_george
        resp_a = client.get("/api/books/the_great_gatsby.pdf/cast", headers={"X-Session-ID": session_a})
        assert resp_a.json()["characters"]["char_tom"]["voice_id"] == "bm_george"

        # Session B should see the default Tom voice (am_adam), NOT Session A's bm_george
        resp_b = client.get("/api/books/the_great_gatsby.pdf/cast", headers={"X-Session-ID": session_b})
        assert resp_b.json()["characters"]["char_tom"]["voice_id"] != "bm_george"
    finally:
        shutil.rmtree(web_app.SAMPLES_DIR / "sessions" / session_a, ignore_errors=True)


def test_session_isolated_outputs(client):
    """Verifies that audio output files in Session A are not leaked to Session B."""
    import shutil
    session_a = "usr_test_alpha"
    session_b = "usr_test_beta"

    sess_a_out = web_app.get_session_outputs_dir(session_a)
    test_out = sess_a_out / "Chapter_01_private.wav"
    test_out.write_bytes(b"RIFF" + b"\x00" * 40 + b"WAVEfmt " + b"\x00" * 50)

    try:
        # Session A sees Chapter_01_private.wav
        resp_a = client.get("/api/outputs", headers={"X-Session-ID": session_a})
        names_a = [o["name"] for o in resp_a.json()["outputs"]]
        assert "Chapter_01_private.wav" in names_a

        # Session B does NOT see Chapter_01_private.wav
        resp_b = client.get("/api/outputs", headers={"X-Session-ID": session_b})
        names_b = [o["name"] for o in resp_b.json()["outputs"]]
        assert "Chapter_01_private.wav" not in names_b

        # Session B cannot download Session A's file (403 Forbidden)
        dl_resp = client.get(
            f"/api/outputs/file/sessions/{session_a}/Chapter_01_private.wav",
            headers={"X-Session-ID": session_b}
        )
        assert dl_resp.status_code == 403
    finally:
        shutil.rmtree(web_app.OUTPUTS_DIR / "sessions" / session_a, ignore_errors=True)


def test_websocket_streaming_book_scope(client, monkeypatch):
    """Verifies that scope='book' triggers multi-chapter streaming."""
    mock_director = MagicMock()
    mock_screenplay = Screenplay(
        chapter_index=1,
        scene_index=1,
        lines=[
            ScreenplayLine(speaker="narrator", text="The green light.", emotion="reflective", speed=1.0, pause_after_ms=300),
        ]
    )
    mock_director.direct_scene.return_value = (mock_screenplay, None)
    monkeypatch.setattr(web_app, "get_director", lambda: mock_director)

    mock_synth = MagicMock()
    def mock_stream(screenplay, cast_sheet):
        for i, line in enumerate(screenplay.lines, 1):
            yield i, len(screenplay.lines), line, "bm_george", AudioSegment.silent(duration=200)

    mock_synth.stream_scene_lines = mock_stream
    monkeypatch.setattr(web_app, "get_synthesizer", lambda: mock_synth)

    with client.websocket_connect("/ws/stream/the_great_gatsby.pdf") as websocket:
        websocket.send_json({"action": "start", "chapter": 1, "scope": "book", "all_chapters": True})

        msg1 = websocket.receive_json()
        assert msg1["type"] == "started"
        assert msg1["scope"] == "book"
        assert msg1["total_chapters"] > 1

        # Check first chapter events
        msg_ch = websocket.receive_json()
        assert msg_ch["type"] == "chapter_start"
        assert msg_ch["chapter_index"] == 1


