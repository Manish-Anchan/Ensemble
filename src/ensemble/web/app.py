import io
import os
import json
import time
import base64
import asyncio
import logging
import traceback
from typing import Dict, Any, List, Optional
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Response
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

logger = logging.getLogger("ensemble.web")

from ensemble.parser.extractor import load_book
from ensemble.parser.models import Book, Chapter, SceneChunk
from ensemble.producer.models import CastSheet, CharacterProfile
from ensemble.producer.catalog import KOKORO_VOICE_CATALOG, VoiceDescriptor
from ensemble.producer.casting import CastingProducer
from ensemble.director.director import SceneDirector
from ensemble.audio.synthesizer import DramaSynthesizer


app = FastAPI(title="Ensemble Audio Drama Studio", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base Directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SAMPLES_DIR = PROJECT_ROOT / "samples"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
STATIC_DIR = Path(__file__).resolve().parent / "static"
DIST_DIR = Path(__file__).resolve().parent / "dist"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Mount static and React dist assets
if (DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Shared In-Memory Caches & Singletons
_books_cache: Dict[str, Book] = {}
_synthesizer: Optional[DramaSynthesizer] = None
_director: Optional[SceneDirector] = None
_voice_samples_cache: Dict[str, bytes] = {}

# Dedicated background worker thread pool for heavy LLM & ONNX synthesis
_worker_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ensemble_worker")


def get_synthesizer() -> DramaSynthesizer:
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = DramaSynthesizer()
    return _synthesizer


def get_director() -> SceneDirector:
    global _director
    if _director is None:
        _director = SceneDirector()
    return _director


def get_cached_book(filename: str) -> Book:
    """Loads a book or fetches it from in-memory cache."""
    file_path = SAMPLES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Book file not found: {filename}")

    cache_key = f"{filename}_{file_path.stat().st_mtime}"
    if cache_key not in _books_cache:
        # Load and parse book
        book = load_book(file_path)
        _books_cache[cache_key] = book

    return _books_cache[cache_key]


def find_cast_sheet(book_stem: str) -> Optional[Path]:
    """Finds cast sheet file for a given book stem in samples/ or outputs/."""
    candidates = [
        SAMPLES_DIR / f"{book_stem}_cast.json",
        OUTPUTS_DIR / book_stem / "cast_sheet.json",
        SAMPLES_DIR / "cast_sheet.json",
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > 10:
            return p
    return None


# ==============================================================================
# Web & UI Endpoints
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    react_index = DIST_DIR / "index.html"
    if react_index.exists():
        with open(react_index, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Ensemble Studio UI is initializing...</h1>", status_code=200)
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ==============================================================================
# REST API: Books & Library
# ==============================================================================

@app.get("/api/books")
async def list_books():
    """Returns all available books in samples/ with metadata."""
    books = []
    if SAMPLES_DIR.exists():
        for f in sorted(SAMPLES_DIR.iterdir()):
            if f.suffix.lower() in (".pdf", ".epub"):
                stem = f.stem
                cast_path = find_cast_sheet(stem)
                books.append({
                    "filename": f.name,
                    "title": stem.replace("_", " ").title(),
                    "size_bytes": f.stat().st_size,
                    "format": f.suffix.lower().lstrip("."),
                    "has_cast_sheet": cast_path is not None,
                    "cast_sheet_path": str(cast_path.relative_to(PROJECT_ROOT)) if cast_path else None,
                })
    return {"books": books}


@app.post("/api/upload")
async def upload_book(file: UploadFile = File(...)):
    """Uploads a PDF or EPUB book to the samples directory."""
    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".epub"):
        raise HTTPException(status_code=400, detail="Only .pdf and .epub files are supported.")

    dest = SAMPLES_DIR / file.filename
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    # Invalidate cache if re-uploaded
    for k in list(_books_cache.keys()):
        if k.startswith(file.filename):
            del _books_cache[k]

    return {
        "filename": file.filename,
        "size_bytes": len(content),
        "status": "uploaded",
    }


@app.get("/api/books/{filename}/chapters")
async def get_book_chapters(filename: str):
    """Returns the parsed chapters and scenes list for a book."""
    try:
        book = get_cached_book(filename)
        chapters = []
        for ch in book.chapters:
            chapters.append({
                "index": ch.index,
                "title": ch.title,
                "scene_count": len(ch.scenes),
                "word_count": ch.word_count,
            })
        return {
            "title": book.title,
            "author": book.author or "Unknown",
            "total_chapters": len(book.chapters),
            "total_words": book.total_words,
            "chapters": chapters,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse book: {str(e)}")


# ==============================================================================
# REST API: Casting & Voice Catalog
# ==============================================================================

@app.get("/api/voices")
async def list_voices():
    """Returns the catalog of 28 Kokoro voices grouped by gender and accent."""
    catalog = []
    for vid, v in KOKORO_VOICE_CATALOG.items():
        catalog.append({
            "voice_id": v.voice_id,
            "name": v.name,
            "gender": v.gender,
            "accent": v.accent,
            "age_group": v.age_group,
            "timbre": v.timbre,
            "description": v.description,
        })
    return {"voices": catalog}


def _generate_wav_sample(voice_id: str, voice: VoiceDescriptor) -> bytes:
    synth = get_synthesizer()
    sample_text = f"Hello, I am {voice.name}. Ready to bring your characters to life in full dramatic sound."
    lang = "en-gb" if voice.accent == "british" else "en-us"
    audio_seg = synth.synthesize_line(sample_text, voice_id=voice_id, speed=1.0, lang=lang)
    buf = io.BytesIO()
    audio_seg.export(buf, format="wav")
    return buf.getvalue()


@app.get("/api/voice-sample/{voice_id}")
async def get_voice_sample(voice_id: str):
    """Generates or returns a cached voice preview sample as WAV audio."""
    if voice_id not in KOKORO_VOICE_CATALOG:
        raise HTTPException(status_code=404, detail=f"Unknown voice: {voice_id}")

    if voice_id in _voice_samples_cache:
        return Response(content=_voice_samples_cache[voice_id], media_type="audio/wav")

    voice = KOKORO_VOICE_CATALOG[voice_id]
    try:
        wav_bytes = await asyncio.to_thread(_generate_wav_sample, voice_id, voice)
        _voice_samples_cache[voice_id] = wav_bytes
        return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")


@app.get("/api/books/{filename}/cast")
async def get_cast(filename: str):
    """Returns the cast sheet for a book."""
    stem = Path(filename).stem
    cast_path = find_cast_sheet(stem)

    if not cast_path:
        return {
            "exists": False,
            "book_title": stem.replace("_", " ").title(),
            "characters": {},
            "narrator_id": "narrator",
        }

    cast_sheet = CastSheet.load_json(cast_path)
    return {
        "exists": True,
        "book_title": cast_sheet.book_title,
        "narrator_id": cast_sheet.narrator_id,
        "characters": {k: p.__dict__ for k, p in cast_sheet.characters.items()},
    }


class CastUpdateRequest(BaseModel):
    book_title: Optional[str] = "Untitled"
    narrator_id: Optional[str] = "narrator"
    characters: Dict[str, Dict[str, Any]]


@app.post("/api/books/{filename}/cast")
async def update_cast(filename: str, req: CastUpdateRequest):
    """Updates and persists the cast sheet for a book."""
    stem = Path(filename).stem
    target_path = SAMPLES_DIR / f"{stem}_cast.json"

    chars: Dict[str, CharacterProfile] = {}
    for cid, cdata in req.characters.items():
        chars[cid] = CharacterProfile(
            id=cid,
            name=cdata.get("name", cid),
            gender=cdata.get("gender", "unknown"),
            age_group=cdata.get("age_group", "adult"),
            role=cdata.get("role", "supporting"),
            personality_traits=cdata.get("personality_traits", []),
            aliases=cdata.get("aliases", []),
            voice_id=cdata.get("voice_id", "bm_george"),
            voice_rationale=cdata.get("voice_rationale", ""),
        )

    cast_sheet = CastSheet(
        book_title=req.book_title or stem.replace("_", " ").title(),
        characters=chars,
        narrator_id=req.narrator_id or "narrator",
    )
    cast_sheet.save_json(target_path)

    return {
        "status": "saved",
        "cast_path": str(target_path.relative_to(PROJECT_ROOT)),
        "characters_count": len(chars),
    }


# ==============================================================================
# REST API: Outputs & Mastered Tracks
# ==============================================================================

@app.get("/api/outputs")
async def list_outputs():
    """Lists all produced audio files in the outputs directory."""
    results = []
    if OUTPUTS_DIR.exists():
        for root, _, files in os.walk(OUTPUTS_DIR):
            for file in sorted(files):
                if file.lower().endswith((".wav", ".mp3", ".json")):
                    file_path = Path(root) / file
                    rel_path = file_path.relative_to(OUTPUTS_DIR)
                    size = file_path.stat().st_size
                    ext = file_path.suffix.lower().lstrip(".")

                    dur_sec = 0.0
                    if ext == "wav" and size > 44:
                        dur_sec = round((size - 44) / 48000.0, 1)
                    elif ext == "mp3" and size > 1000:
                        dur_sec = round(size / 16000.0, 1)

                    results.append({
                        "name": file,
                        "relative_path": str(rel_path),
                        "format": ext,
                        "size_bytes": size,
                        "duration_sec": dur_sec,
                        "modified_at": file_path.stat().st_mtime,
                    })
    return {"outputs": results}


@app.get("/api/outputs/file/{path:path}")
async def get_output_file(path: str):
    """Serves a produced audio file for playback or download."""
    target = (OUTPUTS_DIR / path).resolve()
    if not target.is_relative_to(OUTPUTS_DIR.resolve()) or not target.exists():
        raise HTTPException(status_code=404, detail="File not found")

    ext = target.suffix.lower()
    media_type = "audio/mpeg" if ext == ".mp3" else ("audio/wav" if ext == ".wav" else "application/json")
    return FileResponse(target, media_type=media_type, filename=target.name)


# ==============================================================================
# WebSocket: Live Drama Streaming Pipeline
# ==============================================================================

@app.websocket("/ws/stream/{filename}")
async def websocket_drama_stream(websocket: WebSocket, filename: str):
    """
    Live streaming engine over WebSocket.
    Client connects, initiates stream with chapter/scene params,
    and server directs screenplay & streams audio line-by-line in real-time.
    """
    await websocket.accept()

    try:
        book = get_cached_book(filename)
        stem = Path(filename).stem
        cast_path = find_cast_sheet(stem)

        if cast_path:
            cast_sheet = CastSheet.load_json(cast_path)
        else:
            # Fallback auto-cast on worker executor so event loop is not blocked
            producer = CastingProducer()
            loop = asyncio.get_running_loop()
            cast_sheet = await loop.run_in_executor(_worker_executor, producer.cast_book, book)
            saved_cast_path = SAMPLES_DIR / f"{stem}_cast.json"
            try:
                cast_sheet.save_json(saved_cast_path)
            except Exception as e:
                logger.warning(f"Failed to persist auto-cast sheet: {e}")

        synth = get_synthesizer()
        director = get_director()

        # Listen for start command
        init_data = await websocket.receive_json()
        action = init_data.get("action", "start")
        if action not in ("start", "start_chapter_stream"):
            await websocket.send_json({"type": "error", "message": f"Unknown action: {action}"})
            await websocket.close()
            return

        target_ch_idx = int(init_data.get("chapter") or init_data.get("chapter_index") or 1)
        max_scenes = int(init_data.get("scenes", 0))  # 0 means all scenes in chapter

        # Locate target chapter
        target_chapter = next((ch for ch in book.chapters if ch.index == target_ch_idx), None)
        if not target_chapter:
            await websocket.send_json({
                "type": "error",
                "message": f"Chapter {target_ch_idx} not found in {book.title}"
            })
            await websocket.close()
            return

        scenes_to_stream = target_chapter.scenes
        if max_scenes > 0:
            scenes_to_stream = target_chapter.scenes[:max_scenes]

        await websocket.send_json({
            "type": "started",
            "book_title": book.title,
            "chapter_index": target_chapter.index,
            "chapter_title": target_chapter.title,
            "total_scenes": len(scenes_to_stream),
        })

        loop = asyncio.get_running_loop()
        stop_event = threading.Event()
        queue: asyncio.Queue = asyncio.Queue(maxsize=40)

        def push_item(item):
            if stop_event.is_set():
                return
            fut = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
            while not stop_event.is_set():
                try:
                    fut.result(timeout=0.1)
                    return
                except FutureTimeoutError:
                    continue
                except Exception:
                    return

        def producer_worker():
            """Worker thread: runs heavy LLM directing & ONNX synthesis without blocking asyncio loop."""
            nonlocal cast_sheet
            global_line_counter = 0
            try:
                for s_idx, scene in enumerate(scenes_to_stream, 1):
                    if stop_event.is_set():
                        break

                    push_item({
                        "type": "scene_start",
                        "scene_index": scene.scene_index,
                        "current_scene_number": s_idx,
                        "total_scenes": len(scenes_to_stream),
                        "word_count": scene.word_count,
                    })

                    # Direct screenplay (LLM call off the event loop)
                    t0 = time.time()
                    screenplay, updated_cast = director.direct_scene(
                        scene=scene,
                        cast_sheet=cast_sheet,
                        chapter_index=scene.chapter_index,
                        scene_index=scene.scene_index,
                    )
                    cast_sheet = updated_cast or cast_sheet
                    direct_dur = time.time() - t0

                    if stop_event.is_set():
                        break

                    lines_meta = []
                    scene_start_global_idx = global_line_counter
                    for s_line_idx, line in enumerate(screenplay.lines, 1):
                        global_line_counter += 1
                        char = cast_sheet.get_character_for_speaker(line.speaker)
                        lines_meta.append({
                            "line_index": global_line_counter,
                            "scene_line_index": s_line_idx,
                            "scene_index": scene.scene_index,
                            "speaker": line.speaker,
                            "character_name": char.name if char else line.speaker.replace("char_", "").replace("_", " ").title(),
                            "text": line.text,
                            "emotion": line.emotion,
                            "speed": line.speed,
                            "pause_after_ms": line.pause_after_ms,
                            "voice_id": cast_sheet.get_voice_for_speaker(line.speaker),
                        })

                    push_item({
                        "type": "screenplay_ready",
                        "scene_index": scene.scene_index,
                        "scene_number": s_idx,
                        "total_lines": len(screenplay.lines),
                        "lines": lines_meta,
                        "direct_duration_sec": round(direct_dur, 2),
                    })

                    # Stream audio lines (ONNX inference off the event loop)
                    audio_line_counter = scene_start_global_idx
                    for line_idx, total_lines, line, voice_id, line_audio in synth.stream_scene_lines(screenplay, cast_sheet):
                        if stop_event.is_set():
                            break

                        audio_line_counter += 1
                        buf = io.BytesIO()
                        line_audio.export(buf, format="wav")
                        wav_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

                        char = cast_sheet.get_character_for_speaker(line.speaker)
                        char_name = char.name if char else line.speaker.replace("char_", "").replace("_", " ").title()

                        payload = {
                            "type": "line_audio",
                            "scene_index": scene.scene_index,
                            "line_index": audio_line_counter,
                            "scene_line_index": line_idx,
                            "total_lines": total_lines,
                            "speaker": line.speaker,
                            "character_name": char_name,
                            "voice_id": voice_id,
                            "emotion": line.emotion,
                            "speed": line.speed,
                            "pause_after_ms": line.pause_after_ms,
                            "duration_ms": len(line_audio),
                            "text": line.text,
                            "audio_base64": wav_b64,
                        }
                        push_item(payload)

                    if stop_event.is_set():
                        break

                    push_item({
                        "type": "scene_completed",
                        "scene_index": scene.scene_index,
                    })

                if not stop_event.is_set():
                    push_item({
                        "type": "finished",
                        "message": "All scenes streamed successfully.",
                    })

            except Exception as exc:
                raw_err = str(exc)
                logger.error(f"Streaming error in producer_worker: {raw_err}\n{traceback.format_exc()}")
                if "rate_limit" in raw_err.lower() or "429" in raw_err or "tpm" in raw_err.lower() or "otpm" in raw_err.lower():
                    clean_msg = "Director hit a temporary provider rate limit. Please pause for 5 seconds and resume."
                elif "timeout" in raw_err.lower():
                    clean_msg = "Request to the AI Director timed out. Please retry."
                elif "connection" in raw_err.lower():
                    clean_msg = "Connection interrupted while directing audio drama."
                else:
                    clean_msg = "A temporary issue occurred while directing this scene. Please retry."
                push_item({"type": "error", "message": clean_msg, "code": "streaming_error"})
            finally:
                push_item(None)

        # Launch producer in worker thread
        producer_future = loop.run_in_executor(_worker_executor, producer_worker)

        # Consumer task: forwards queue items to websocket
        async def consumer():
            try:
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    await websocket.send_json(item)
                    queue.task_done()
            except (WebSocketDisconnect, RuntimeError, ConnectionResetError):
                stop_event.set()

        # Listener task: listens for incoming client stop/pause
        async def listener():
            try:
                while not stop_event.is_set():
                    data = await websocket.receive_json()
                    action = data.get("action")
                    if action in ("stop", "close"):
                        stop_event.set()
                        break
            except (WebSocketDisconnect, RuntimeError, ConnectionResetError):
                stop_event.set()

        consumer_task = asyncio.create_task(consumer())
        listener_task = asyncio.create_task(listener())

        done, pending = await asyncio.wait(
            [consumer_task, listener_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        stop_event.set()
        for t in pending:
            t.cancel()

        await producer_future

    except WebSocketDisconnect:
        # Client closed connection
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
