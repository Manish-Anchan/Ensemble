import io
import os
import re
import json
import time
import base64
import asyncio
import logging
import traceback
from typing import Dict, Any, List, Optional
from pathlib import Path

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
    HTTPException,
    Response,
    Header,
    Query,
    Depends,
)
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


def sanitize_session_id(session_id: Optional[str]) -> Optional[str]:
    """Sanitizes session ID to prevent path traversal, allowing alphanumeric and dashes/underscores only."""
    if not session_id or not isinstance(session_id, str):
        return None
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "", session_id.strip())
    return cleaned[:64] if cleaned else None


def get_session_id(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = Query(None),
) -> Optional[str]:
    """Extracts and sanitizes session ID from header or query parameter."""
    return sanitize_session_id(x_session_id or session_id)


def get_session_samples_dir(session_id: Optional[str] = None) -> Path:
    """Returns the session-isolated samples directory, or global samples directory if none."""
    clean_id = sanitize_session_id(session_id)
    if clean_id:
        p = SAMPLES_DIR / "sessions" / clean_id
        p.mkdir(parents=True, exist_ok=True)
        return p
    return SAMPLES_DIR


def get_session_outputs_dir(session_id: Optional[str] = None) -> Path:
    """Returns the session-isolated outputs directory, or global outputs directory if none."""
    clean_id = sanitize_session_id(session_id)
    if clean_id:
        p = OUTPUTS_DIR / "sessions" / clean_id
        p.mkdir(parents=True, exist_ok=True)
        return p
    return OUTPUTS_DIR


def get_cached_book(filename: str, session_id: Optional[str] = None) -> Book:
    """Loads a book or fetches it from in-memory cache, checking session dir first then global."""
    clean_sid = sanitize_session_id(session_id)
    file_path: Optional[Path] = None
    if clean_sid:
        sess_path = get_session_samples_dir(clean_sid) / filename
        if sess_path.exists():
            file_path = sess_path

    if file_path is None:
        global_path = SAMPLES_DIR / filename
        if global_path.exists():
            file_path = global_path

    if file_path is None or not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Book file not found: {filename}")

    cache_key = f"{str(file_path)}_{file_path.stat().st_mtime}"
    if cache_key not in _books_cache:
        # Load and parse book
        book = load_book(file_path)
        _books_cache[cache_key] = book

    return _books_cache[cache_key]


def find_cast_sheet(book_stem: str, session_id: Optional[str] = None) -> Optional[Path]:
    """Finds cast sheet file for a given book stem, prioritizing session-scoped cast sheets."""
    clean_sid = sanitize_session_id(session_id)
    candidates: List[Path] = []
    if clean_sid:
        candidates.extend([
            get_session_samples_dir(clean_sid) / f"{book_stem}_cast.json",
            get_session_outputs_dir(clean_sid) / book_stem / "cast_sheet.json",
        ])
    candidates.extend([
        SAMPLES_DIR / f"{book_stem}_cast.json",
        OUTPUTS_DIR / book_stem / "cast_sheet.json",
        SAMPLES_DIR / "cast_sheet.json",
    ])
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
# REST API: Hardware & System Telemetry
# ==============================================================================

_hardware_cache: Dict[str, Any] = {"data": None, "timestamp": 0.0}

@app.get("/api/hardware")
async def get_hardware_status():
    """Returns GPU / CUDA hardware status, ONNX execution providers, and engine telemetry."""
    now = time.time()
    if _hardware_cache["data"] and (now - _hardware_cache["timestamp"] < 15.0):
        return _hardware_cache["data"]

    import shutil
    import subprocess
    import onnxruntime as ort

    providers = ort.get_available_providers()
    cuda_available = "CUDAExecutionProvider" in providers

    gpu_info = {
        "cuda_available": cuda_available,
        "providers": providers,
        "device_name": "CPU Fallback" if not cuda_available else "NVIDIA GPU",
        "memory_total_mb": None,
        "memory_free_mb": None,
        "memory_used_mb": None,
    }

    if shutil.which("nvidia-smi"):
        try:
            res = await asyncio.to_thread(
                subprocess.run,
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,memory.used", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                if len(parts) >= 4:
                    gpu_info["device_name"] = parts[0]
                    gpu_info["memory_total_mb"] = int(float(parts[1]))
                    gpu_info["memory_free_mb"] = int(float(parts[2]))
                    gpu_info["memory_used_mb"] = int(float(parts[3]))
        except Exception as e:
            logger.debug(f"Failed to query nvidia-smi: {e}")

    result = {
        "status": "online",
        "engine": "Kokoro-82M ONNX",
        "sample_rate": 24000,
        "gpu": gpu_info,
        "active_threads": threading.active_count(),
    }
    _hardware_cache["data"] = result
    _hardware_cache["timestamp"] = now
    return result


# ==============================================================================
# REST API: Books & Library
# ==============================================================================

@app.get("/api/books")
async def list_books(session_id: Optional[str] = Depends(get_session_id)):
    """Returns all available books with metadata, merging global samples with session-isolated uploads."""
    books = []
    seen_filenames = set()

    # 1. Session-isolated books (if session_id provided)
    clean_sid = sanitize_session_id(session_id)
    if clean_sid:
        sess_dir = get_session_samples_dir(clean_sid)
        if sess_dir.exists():
            for f in sorted(sess_dir.iterdir()):
                if f.is_file() and f.suffix.lower() in (".pdf", ".epub"):
                    seen_filenames.add(f.name)
                    stem = f.stem
                    cast_path = find_cast_sheet(stem, clean_sid)
                    cache_key = f"{str(f)}_{f.stat().st_mtime}"
                    cached = _books_cache.get(cache_key)
                    total_chapters = len(cached.chapters) if cached else None
                    total_words = cached.total_words if cached else None
                    author = cached.author if cached else None
                    title = cached.title if (cached and cached.title) else stem.replace("_", " ").title()

                    books.append({
                        "filename": f.name,
                        "title": title,
                        "author": author or "Uploaded Novel",
                        "size_bytes": f.stat().st_size,
                        "format": f.suffix.lower().lstrip("."),
                        "has_cast_sheet": cast_path is not None,
                        "cast_sheet_path": str(cast_path.relative_to(PROJECT_ROOT)) if cast_path else None,
                        "total_chapters": total_chapters,
                        "total_words": total_words,
                        "is_session_book": True,
                    })

    # 2. Global shared sample books in samples/ (excluding subdirectories like 'sessions')
    if SAMPLES_DIR.exists():
        for f in sorted(SAMPLES_DIR.iterdir()):
            if f.is_file() and f.name not in seen_filenames and f.suffix.lower() in (".pdf", ".epub"):
                stem = f.stem
                cast_path = find_cast_sheet(stem, clean_sid)
                cache_key = f"{str(f)}_{f.stat().st_mtime}"
                cached = _books_cache.get(cache_key)
                total_chapters = len(cached.chapters) if cached else None
                total_words = cached.total_words if cached else None
                author = cached.author if cached else None
                title = cached.title if (cached and cached.title) else stem.replace("_", " ").title()

                books.append({
                    "filename": f.name,
                    "title": title,
                    "author": author or "Classic Literature",
                    "size_bytes": f.stat().st_size,
                    "format": f.suffix.lower().lstrip("."),
                    "has_cast_sheet": cast_path is not None,
                    "cast_sheet_path": str(cast_path.relative_to(PROJECT_ROOT)) if cast_path else None,
                    "total_chapters": total_chapters,
                    "total_words": total_words,
                    "is_session_book": False,
                })
    return {"books": books}


@app.post("/api/upload")
async def upload_book(file: UploadFile = File(...), session_id: Optional[str] = Depends(get_session_id)):
    """Uploads a PDF or EPUB book to the session directory (or samples) and pre-caches it."""
    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".epub"):
        raise HTTPException(status_code=400, detail="Only .pdf and .epub files are supported.")

    target_dir = get_session_samples_dir(session_id)
    dest = target_dir / file.filename
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    # Invalidate cache if re-uploaded
    for k in list(_books_cache.keys()):
        if str(dest) in k:
            del _books_cache[k]

    # Pre-parse book to cache and return instant metadata
    try:
        book = get_cached_book(file.filename, session_id)
        title = book.title or file.filename.replace("_", " ").title()
        total_chapters = len(book.chapters)
        total_words = book.total_words
        author = book.author or "Uploaded Novel"
    except Exception as e:
        title = Path(file.filename).stem.replace("_", " ").title()
        total_chapters = 0
        total_words = 0
        author = "Uploaded Novel"

    return {
        "filename": file.filename,
        "title": title,
        "author": author,
        "total_chapters": total_chapters,
        "total_words": total_words,
        "size_bytes": len(content),
        "status": "uploaded",
        "session_id": session_id,
    }


@app.get("/api/books/{filename}/chapters")
async def get_book_chapters(filename: str, session_id: Optional[str] = Depends(get_session_id)):
    """Returns the parsed chapters and scenes list for a book."""
    try:
        book = get_cached_book(filename, session_id)
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
async def get_cast(filename: str, session_id: Optional[str] = Depends(get_session_id)):
    """Returns the cast sheet for a book, prioritizing session-scoped cast."""
    stem = Path(filename).stem
    cast_path = find_cast_sheet(stem, session_id)

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
async def update_cast(
    filename: str,
    req: CastUpdateRequest,
    session_id: Optional[str] = Depends(get_session_id),
):
    """Updates and persists the cast sheet for a book in session or global directory."""
    stem = Path(filename).stem
    target_dir = get_session_samples_dir(session_id)
    target_path = target_dir / f"{stem}_cast.json"

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
async def list_outputs(session_id: Optional[str] = Depends(get_session_id)):
    """Lists produced audio files for the session (or global outputs), strictly excluding other sessions."""
    results = []
    clean_sid = sanitize_session_id(session_id)

    # 1. Session outputs (if session_id active)
    if clean_sid:
        sess_out_dir = get_session_outputs_dir(clean_sid)
        if sess_out_dir.exists():
            for root, _, files in os.walk(sess_out_dir):
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

    # 2. Global outputs directly in outputs/ (excluding 'sessions/' entirely)
    if OUTPUTS_DIR.exists():
        for root, dirs, files in os.walk(OUTPUTS_DIR):
            if "sessions" in dirs:
                dirs.remove("sessions")
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
async def get_output_file(path: str, session_id: Optional[str] = Depends(get_session_id)):
    """Serves a produced audio file, enforcing session isolation for session files."""
    target = (OUTPUTS_DIR / path).resolve()
    if not target.is_relative_to(OUTPUTS_DIR.resolve()) or not target.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # If the file is inside sessions/, ensure it belongs to the requesting session
    clean_sid = sanitize_session_id(session_id)
    try:
        rel = target.relative_to((OUTPUTS_DIR / "sessions").resolve())
        file_sid = rel.parts[0]
        if not clean_sid or file_sid != clean_sid:
            raise HTTPException(status_code=403, detail="Access denied to another session's file.")
    except ValueError:
        # File is not inside sessions/, so it's a shared global output
        pass

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
        session_id = sanitize_session_id(websocket.query_params.get("session_id"))

        synth = get_synthesizer()
        director = get_director()

        # Listen for start command
        init_data = await websocket.receive_json()
        action = init_data.get("action", "start")
        if action not in ("start", "start_chapter_stream"):
            await websocket.send_json({"type": "error", "message": f"Unknown action: {action}"})
            await websocket.close()
            return

        if not session_id:
            session_id = sanitize_session_id(init_data.get("session_id"))

        book = get_cached_book(filename, session_id)
        stem = Path(filename).stem
        cast_path = find_cast_sheet(stem, session_id)

        if cast_path:
            cast_sheet = CastSheet.load_json(cast_path)
        else:
            # Fallback auto-cast on worker executor so event loop is not blocked
            producer = CastingProducer()
            loop = asyncio.get_running_loop()
            cast_sheet = await loop.run_in_executor(_worker_executor, producer.cast_book, book)
            saved_cast_path = get_session_samples_dir(session_id) / f"{stem}_cast.json"
            try:
                cast_sheet.save_json(saved_cast_path)
            except Exception as e:
                logger.warning(f"Failed to persist auto-cast sheet: {e}")

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
            last_scene_text: Optional[str] = None
            last_active_speakers: List[str] = []
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

                    # Build rolling previous scene context for pronoun and character continuity
                    previous_scene_context = None
                    if last_scene_text:
                        words = last_scene_text.strip().split()
                        trailing_words = " ".join(words[-200:]) if len(words) > 200 else last_scene_text.strip()
                        speakers_hint = f"Characters active in previous scene: {', '.join(last_active_speakers)}\n" if last_active_speakers else ""
                        previous_scene_context = f"{speakers_hint}Ending of previous scene:\n\"{trailing_words}\""
                    elif scene.scene_index > 1:
                        prev_scene_obj = next((s for s in target_chapter.scenes if s.scene_index == scene.scene_index - 1), None)
                        if prev_scene_obj and prev_scene_obj.text:
                            words = prev_scene_obj.text.strip().split()
                            trailing_words = " ".join(words[-200:]) if len(words) > 200 else prev_scene_obj.text.strip()
                            previous_scene_context = f"Ending of preceding scene:\n\"{trailing_words}\""

                    # Direct screenplay (LLM call off the event loop)
                    t0 = time.time()
                    screenplay, updated_cast = director.direct_scene(
                        scene=scene,
                        cast_sheet=cast_sheet,
                        chapter_index=scene.chapter_index,
                        scene_index=scene.scene_index,
                        previous_scene_context=previous_scene_context,
                    )
                    cast_sheet = updated_cast or cast_sheet
                    direct_dur = time.time() - t0

                    last_scene_text = scene.text
                    last_active_speakers = [
                        cast_sheet.characters[spk].name for spk in screenplay.speaker_counts.keys()
                        if spk in cast_sheet.characters and spk != "narrator"
                    ]

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
