import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { VoiceOrb } from './components/VoiceOrb';
import {
  StudioAudioEngine,
  type LineMetadata,
  type AudioFrequencyData
} from './lib/audioEngine';

interface BookItem {
  filename: string;
  title: string;
  author: string;
  size_bytes: number;
  format: string;
  has_cast_sheet: boolean;
  total_chapters?: number;
  total_words?: number;
}

interface ChapterItem {
  index: number;
  title: string;
  scene_count: number;
  word_count: number;
}

interface CharacterProfile {
  id: string;
  name: string;
  gender: string;
  age_group: string;
  role: string;
  personality_traits: string[];
  aliases: string[];
  voice_id: string;
  voice_rationale: string;
}

interface CastSheetData {
  exists: boolean;
  book_title: string;
  narrator_id: string;
  characters: Record<string, CharacterProfile>;
}

interface VoiceDescriptor {
  voice_id: string;
  name: string;
  gender: string;
  accent: string;
  age_group: string;
  timbre: string;
  description: string;
}

interface HardwareStatus {
  status: string;
  engine: string;
  sample_rate: number;
  gpu: {
    cuda_available: boolean;
    device_name: string;
    memory_total_mb: number | null;
    memory_free_mb: number | null;
    memory_used_mb: number | null;
  };
}

interface OutputTrack {
  name: string;
  relative_path: string;
  format: string;
  size_bytes: number;
  duration_sec: number;
  modified_at: number;
}

const PASTEL_PALETTE = [
  '#7fe6e3',
  '#f4a3dc',
  '#8fb8ff',
  '#ffd180',
  '#b8e994',
  '#ffaaa5',
  '#c7ecee',
  '#e8d07a',
  '#dcd6f7',
];

function getCharacterColor(name: string): string {
  const lower = (name || '').toLowerCase();
  if (lower.includes('narrator')) return '#b9a6ff';
  let hash = 0;
  for (let i = 0; i < lower.length; i++) {
    hash = (hash << 5) - hash + lower.charCodeAt(i);
    hash |= 0;
  }
  const index = Math.abs(hash) % PASTEL_PALETTE.length;
  return PASTEL_PALETTE[index];
}

export default function App() {
  // Navigation & Drawers
  const [castingDrawerOpen, setCastingDrawerOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  // Books & Chapters State
  const [books, setBooks] = useState<BookItem[]>([]);
  const [selectedBook, setSelectedBook] = useState<string | null>(null);
  const [chapters, setChapters] = useState<ChapterItem[]>([]);
  const [selectedChapter, setSelectedChapter] = useState<number>(1);
  const [activeScope, setActiveScope] = useState<'chapter' | 'scene'>('chapter');

  // Casting & Voices State
  const [voices, setVoices] = useState<VoiceDescriptor[]>([]);
  const [castSheet, setCastSheet] = useState<CastSheetData | null>(null);
  const [isSavingCast, setIsSavingCast] = useState(false);
  const [auditioningVoiceId, setAuditioningVoiceId] = useState<string | null>(null);

  // Hardware Status State
  const [hardware, setHardware] = useState<HardwareStatus | null>(null);

  // Mastered Outputs State
  const [outputs, setOutputs] = useState<OutputTrack[]>([]);

  // Streaming & Playback State
  const [isStreaming, setIsStreaming] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [streamingStatus, setStreamingStatus] = useState<string>('Ready');
  const [volume, setVolume] = useState<number>(1.0);
  const [toastMessage, setToastMessage] = useState<{ title: string; text: string; type: 'info' | 'error' | 'success' } | null>(null);

  // Screenplay Lines & Real-time Speaker
  const [lines, setLines] = useState<LineMetadata[]>([]);
  const [activeLineIndex, setActiveLineIndex] = useState<number>(0);
  const [activeSpeaker, setActiveSpeaker] = useState<{ name: string; role: string }>({
    name: 'Story Narrator',
    role: 'NARRATOR',
  });

  // Jitter Buffer Metrics
  const [bufferedCount, setBufferedCount] = useState<number>(0);
  const [bufferedSec, setBufferedSec] = useState<number>(0);

  // Auto-follow scroll state
  const [following, setFollowing] = useState<boolean>(true);
  const followingRef = useRef<boolean>(true);
  followingRef.current = following;
  const linesContainerRef = useRef<HTMLDivElement | null>(null);
  const lastProgrammaticScrollRef = useRef<number>(0);

  // Audio Telemetry
  const [freq, setFreq] = useState<AudioFrequencyData>({ energy: 0, bass: 0, mid: 0, treble: 0 });

  // Web Audio Engine Singleton
  const audioEngine = useMemo(() => new StudioAudioEngine(), []);
  const socketRef = useRef<WebSocket | null>(null);

  // ---------------------------------------------------------------------------
  // Auto-follow scrolling inside .lines container
  // ---------------------------------------------------------------------------
  const scrollToLine = useCallback((lineIndex: number, smooth = true) => {
    const container = linesContainerRef.current;
    if (!container) return;
    const lineEl = document.getElementById(`script-line-${lineIndex}`);
    if (!lineEl) return;

    const top = lineEl.offsetTop - container.clientHeight * 0.35;
    lastProgrammaticScrollRef.current = Date.now();
    container.scrollTo({
      top: Math.max(0, top),
      behavior: smooth ? 'smooth' : 'auto',
    });
  }, []);

  const handleUserScrollInteraction = useCallback(() => {
    if (followingRef.current) {
      followingRef.current = false;
      setFollowing(false);
    }
  }, []);

  const handleJumpToLive = useCallback(() => {
    followingRef.current = true;
    setFollowing(true);
    scrollToLine(activeLineIndex, true);
  }, [activeLineIndex, scrollToLine]);

  const handleLineClick = (lineIndex: number) => {
    setActiveLineIndex(lineIndex);
    followingRef.current = true;
    setFollowing(true);
    scrollToLine(lineIndex, true);
  };

  // Scroll to active line whenever activeLineIndex changes, if following is active
  useEffect(() => {
    if (followingRef.current) {
      scrollToLine(activeLineIndex, true);
    }
  }, [activeLineIndex, scrollToLine]);

  // ---------------------------------------------------------------------------
  // 1. Initial Data Fetching (Books, Voices, Hardware, Outputs)
  // ---------------------------------------------------------------------------
  const fetchBooks = useCallback(async () => {
    try {
      const res = await fetch('/api/books');
      if (res.ok) {
        const data = await res.json();
        const bookList: BookItem[] = data.books || [];
        setBooks(bookList);
        if (bookList.length > 0 && !selectedBook) {
          setSelectedBook(bookList[0].filename);
        }
      }
    } catch (e) {
      console.error('Failed to load books:', e);
    }
  }, [selectedBook]);

  const fetchVoices = useCallback(async () => {
    try {
      const res = await fetch('/api/voices');
      if (res.ok) {
        const data = await res.json();
        setVoices(data.voices || []);
      }
    } catch (e) {
      console.error('Failed to load voices:', e);
    }
  }, []);

  const fetchHardware = useCallback(async () => {
    try {
      const res = await fetch('/api/hardware');
      if (res.ok) {
        const data = await res.json();
        setHardware(data);
      }
    } catch (e) {
      console.error('Failed to load hardware status:', e);
    }
  }, []);

  const fetchOutputs = useCallback(async () => {
    try {
      const res = await fetch('/api/outputs');
      if (res.ok) {
        const data = await res.json();
        setOutputs(data.outputs || []);
      }
    } catch (e) {
      console.error('Failed to load outputs:', e);
    }
  }, []);

  useEffect(() => {
    fetchBooks();
    fetchVoices();
    fetchHardware();
    fetchOutputs();
  }, [fetchBooks, fetchVoices, fetchHardware, fetchOutputs]);

  // ---------------------------------------------------------------------------
  // 2. Load Book Chapters & Cast Sheet when Selected Book Changes
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!selectedBook) return;

    fetch(`/api/books/${selectedBook}/chapters`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && data.chapters) {
          setChapters(data.chapters);
          setSelectedChapter(data.chapters[0]?.index || 1);
        }
      })
      .catch((err) => console.error('Failed to load chapters:', err));

    fetch(`/api/books/${selectedBook}/cast`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setCastSheet(data);
      })
      .catch((err) => console.error('Failed to load cast:', err));
  }, [selectedBook]);

  // ---------------------------------------------------------------------------
  // 3. Audio Engine Event Listeners
  // ---------------------------------------------------------------------------
  useEffect(() => {
    audioEngine.onFrequencyChange = (f) => {
      setFreq(f);
    };

    audioEngine.onBufferProgress = (count, _target, totalSec) => {
      setBufferedCount(count);
      setBufferedSec(totalSec);
      if (audioEngine.isBuffering) {
        setStreamingStatus(`Buffering (${count} lines · ${totalSec.toFixed(1)}s)...`);
      }
    };

    audioEngine.onLineStart = (meta) => {
      setActiveLineIndex(meta.line_index);
      setActiveSpeaker({
        name: meta.character_name || meta.speaker,
        role: meta.speaker === 'narrator' ? 'NARRATOR' : 'CHARACTER',
      });
      setStreamingStatus('Streaming 24kHz Audio');
    };

    audioEngine.onPlaybackStateChange = (playing) => {
      setIsPlaying(playing);
    };

    audioEngine.onQueueEmpty = () => {
      if (audioEngine.isStreamComplete) {
        setStreamingStatus('Chapter Complete');
        setIsPlaying(false);
        setIsPaused(false);
        setIsStreaming(false);
        fetchOutputs();
      }
    };
  }, [audioEngine, fetchOutputs]);

  useEffect(() => {
    return () => {
      audioEngine.destroy();
    };
  }, [audioEngine]);

  // ---------------------------------------------------------------------------
  // 4. WebSocket Streaming Pipeline (/ws/stream/{filename})
  // ---------------------------------------------------------------------------
  const startDramaStream = () => {
    if (!selectedBook) return;

    audioEngine.ensureContext();
    if (audioEngine.ctx && audioEngine.ctx.state === 'suspended') {
      audioEngine.ctx.resume().catch((e) => console.warn('AudioContext resume failed:', e));
    }

    if (socketRef.current) {
      try {
        socketRef.current.onopen = null;
        socketRef.current.onmessage = null;
        socketRef.current.onerror = null;
        socketRef.current.onclose = null;
        if (socketRef.current.readyState === WebSocket.OPEN) {
          socketRef.current.send(JSON.stringify({ action: 'stop' }));
        }
        socketRef.current.close();
      } catch (e) {
        console.warn('Error closing existing socket:', e);
      }
      socketRef.current = null;
    }

    audioEngine.stop();
    audioEngine.clearQueue();
    audioEngine.startFrequencyLoop();
    setLines([]);
    setActiveLineIndex(0);
    followingRef.current = true;
    setFollowing(true);
    setIsStreaming(true);
    setIsPlaying(true);
    setIsPaused(false);
    setStreamingStatus('Connecting to AI Director...');

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/stream/${selectedBook}`;

    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      setStreamingStatus('AI Director analyzing screenplay...');
      ws.send(
        JSON.stringify({
          action: 'start',
          chapter: selectedChapter,
          scenes: activeScope === 'scene' ? 1 : 0,
        })
      );
    };

    ws.onmessage = async (evt) => {
      try {
        if (socketRef.current !== ws) return;

        const msg = JSON.parse(evt.data);

        if (msg.type === 'started') {
          setStreamingStatus(`Directing Chapter ${msg.chapter_index}...`);
        } else if (msg.type === 'scene_start') {
          setStreamingStatus(`Directing Scene ${msg.current_scene_number}/${msg.total_scenes}...`);
        } else if (msg.type === 'screenplay_ready') {
          setLines((prev) => {
            const existingIds = new Set(prev.map((l) => l.line_index));
            const newOnes = (msg.lines || []).filter((l: LineMetadata) => !existingIds.has(l.line_index));
            return [...prev, ...newOnes];
          });
        } else if (msg.type === 'line_audio') {
          await audioEngine.enqueueLine(msg);
          if (!audioEngine.isPlaying && !isPaused) {
            audioEngine.startPlayback();
          }
        } else if (msg.type === 'finished') {
          audioEngine.setStreamComplete(true);
        } else if (msg.type === 'error') {
          setToastMessage({
            title: 'Streaming Error',
            text: msg.message || 'An error occurred during drama synthesis.',
            type: 'error',
          });
          setStreamingStatus('Stream Stopped');
          setIsStreaming(false);
          setIsPlaying(false);
        }
      } catch (err) {
        console.error('WebSocket parse error:', err);
      }
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      if (socketRef.current === ws) {
        setStreamingStatus('Connection Error');
        setIsStreaming(false);
      }
    };

    ws.onclose = () => {
      if (socketRef.current === ws) {
        setIsStreaming(false);
      }
    };
  };

  const pauseDramaStream = async () => {
    await audioEngine.pause();
    setIsPaused(true);
    setIsPlaying(false);
    setStreamingStatus('Paused');
  };

  const resumeDramaStream = async () => {
    audioEngine.ensureContext();
    await audioEngine.resume();
    setIsPaused(false);
    setIsPlaying(true);
    setStreamingStatus('Streaming 24kHz Audio');
    followingRef.current = true;
    setFollowing(true);
    scrollToLine(activeLineIndex, true);
  };

  const stopDramaStream = () => {
    if (socketRef.current) {
      try {
        if (socketRef.current.readyState === WebSocket.OPEN) {
          socketRef.current.send(JSON.stringify({ action: 'stop' }));
        }
        socketRef.current.close();
      } catch {
        // Ignored
      }
      socketRef.current = null;
    }
    audioEngine.stop();
    setIsStreaming(false);
    setIsPlaying(false);
    setIsPaused(false);
    setStreamingStatus('Ready');
    followingRef.current = true;
    setFollowing(true);
    lastProgrammaticScrollRef.current = Date.now();
    linesContainerRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // ---------------------------------------------------------------------------
  // 5. Voice Audition (Web Audio API Preview)
  // ---------------------------------------------------------------------------
  const auditionVoice = async (voiceId: string) => {
    setAuditioningVoiceId(voiceId);
    try {
      await audioEngine.playVoicePreview(`/api/voice-sample/${voiceId}`);
    } catch (err) {
      console.error('Voice audition failed:', err);
    } finally {
      setAuditioningVoiceId(null);
    }
  };

  // ---------------------------------------------------------------------------
  // 6. Save Cast Sheet Updates
  // ---------------------------------------------------------------------------
  const saveCastSheet = async () => {
    if (!selectedBook || !castSheet) return;
    setIsSavingCast(true);
    try {
      const resp = await fetch(`/api/books/${selectedBook}/cast`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          book_title: castSheet.book_title,
          narrator_id: castSheet.narrator_id,
          characters: castSheet.characters,
        }),
      });
      if (resp.ok) {
        setToastMessage({
          title: 'Cast Sheet Saved',
          text: 'Voice assignments successfully updated.',
          type: 'success',
        });
      } else {
        throw new Error('Save failed');
      }
    } catch {
      setToastMessage({
        title: 'Save Failed',
        text: 'Unable to save cast sheet updates.',
        type: 'error',
      });
    } finally {
      setIsSavingCast(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 7. Manuscript File Upload (PDF / EPUB)
  // ---------------------------------------------------------------------------
  const uploadManuscriptFile = async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);

    setStreamingStatus(`Uploading ${file.name}...`);
    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        setToastMessage({
          title: 'Manuscript Ingested',
          text: `"${data.title}" loaded with ${data.total_chapters} chapters.`,
          type: 'success',
        });
        await fetchBooks();
        setSelectedBook(data.filename);
      } else {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || 'Failed to upload manuscript.');
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to upload manuscript.';
      setToastMessage({
        title: 'Upload Error',
        text: errorMsg,
        type: 'error',
      });
    } finally {
      setStreamingStatus('Ready');
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadManuscriptFile(file);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      uploadManuscriptFile(file);
    }
  };

  const currentBookObj = books.find((b) => b.filename === selectedBook);
  const currentChapterObj = chapters.find((c) => c.index === selectedChapter);

  return (
    <div className="app">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="toast">
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: toastMessage.type === 'success' ? '#7ff0b8' : '#fb7185',
              boxShadow: `0 0 10px ${toastMessage.type === 'success' ? '#7ff0b8' : '#fb7185'}`,
              flexShrink: 0,
            }}
          />
          <div>
            <b style={{ display: 'block', fontSize: '12px' }}>{toastMessage.title}</b>
            <span style={{ fontSize: '11px', color: 'var(--muted)', fontFamily: 'var(--mono)' }}>
              {toastMessage.text}
            </span>
          </div>
          <button
            onClick={() => setToastMessage(null)}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--dim)',
              cursor: 'pointer',
              marginLeft: '8px',
              fontSize: '12px',
            }}
          >
            ✕
          </button>
        </div>
      )}

      {/* =========================================================================
          1. LEFT RAIL (Brand, Ingestion, Library, Chapter Index, Outputs)
      ========================================================================= */}
      <aside className="side">
        <div className="brand">
          <div className="mini-orb" />
          <div>
            <b>Ensemble Studio</b>
            <small>Kokoro-82M · 24kHz</small>
          </div>
        </div>

        <div>
          <div className="label">
            <span>Ingest manuscript</span>
            <span>PDF / EPUB</span>
          </div>
          <label
            className={`drop ${isDragging ? 'on' : ''}`}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            style={{ cursor: 'pointer', display: 'block' }}
          >
            <input
              type="file"
              accept=".pdf,.epub"
              style={{ display: 'none' }}
              onChange={handleFileUpload}
            />
            <svg
              viewBox="0 0 24 24"
              fill="none"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 16V5M7 9l5-5 5 5M4 15v3a2 2 0 002 2h12a2 2 0 002-2v-3" />
            </svg>
            <b>Drop a novel here or browse</b>
            <span>Scenes and characters are parsed automatically</span>
          </label>
        </div>

        <div>
          <div className="label">
            <span>Manuscript library</span>
            <span
              onClick={fetchBooks}
              style={{ cursor: 'pointer', opacity: 0.7 }}
              title="Refresh library"
            >
              ↻
            </span>
          </div>
          {books.map((b) => (
            <div
              key={b.filename}
              className={`item ${b.filename === selectedBook ? 'on' : ''}`}
              onClick={() => {
                if (b.filename !== selectedBook) {
                  stopDramaStream();
                  setSelectedBook(b.filename);
                }
              }}
            >
              <svg viewBox="0 0 24 24">
                <path d="M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2zM4 19a2 2 0 012-2h13" />
              </svg>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {b.title}
              </span>
              <span className="fmt">{b.format.toUpperCase()}</span>
            </div>
          ))}
        </div>

        <div>
          <div className="label">
            <span>Chapter index</span>
          </div>
          {chapters.map((c) => (
            <div
              key={c.index}
              className={`chap ${c.index === selectedChapter ? 'on' : ''}`}
              onClick={() => {
                if (c.index !== selectedChapter) {
                  stopDramaStream();
                  setSelectedChapter(c.index);
                  followingRef.current = true;
                  setFollowing(true);
                }
              }}
            >
              <em>{c.title}</em>
              <small>{c.scene_count} {c.scene_count === 1 ? 'scene' : 'scenes'}</small>
            </div>
          ))}
        </div>

        <div>
          <div className="label">
            <span>Mastered outputs</span>
          </div>
          {outputs.length === 0 ? (
            <div style={{ font: '400 11px var(--mono)', color: 'var(--dim)', padding: '6px 4px' }}>
              No mastered tracks yet
            </div>
          ) : (
            outputs.map((track) => (
              <a
                key={track.relative_path}
                href={`/api/outputs/file/${track.relative_path}`}
                download={track.name}
                className="item"
                style={{ textDecoration: 'none' }}
              >
                <svg viewBox="0 0 24 24">
                  <path d="M9 18V6l10-2v12M9 18a3 3 0 11-6 0 3 3 0 016 0zm10-2a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                <span style={{ font: '400 12px var(--mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {track.name}
                </span>
                <span className="fmt">↓</span>
              </a>
            ))
          )}
        </div>
      </aside>

      {/* =========================================================================
          2. CENTRAL STUDIO STAGE & FIXED SCREENPLAY CARD
      ========================================================================= */}
      <section className="main">
        {/* Top Bar (flex: none) */}
        <header className="top">
          <div className="crumb">
            Manuscript <b>{currentBookObj?.title || selectedBook || 'No Book Selected'}</b> / <i>Chapter {selectedChapter}{currentChapterObj?.title ? ` · ${currentChapterObj.title}` : ''}</i>
          </div>
          <div className="chips">
            <span className="chip">
              <span className="d" />
              {hardware?.gpu.device_name || 'NVIDIA GPU'} · {hardware?.gpu.cuda_available !== false ? 'CUDA active' : 'CPU'}
            </span>
            <span className="chip v">
              <span className="d" />
              {hardware?.engine || 'Kokoro-82M'} · {hardware?.sample_rate ? `${hardware.sample_rate / 1000}kHz` : '24kHz'}
            </span>
            <button className="btn" onClick={() => setCastingDrawerOpen(!castingDrawerOpen)}>
              Casting Suite
            </button>
          </div>
        </header>

        {/* Stage with Halo, Orb, Spotlight, and Status (flex: none) */}
        <div className={`stage ${isPlaying ? 'speaking' : ''}`} id="stage">
          <div className="halo" />
          <div className="orb-slot">
            <VoiceOrb
              speakerName={activeSpeaker.name}
              role={activeSpeaker.role}
              isPlaying={isPlaying || (isStreaming && !isPaused)}
              freq={freq}
            />
          </div>
          <div className="who">
            <h2>{activeSpeaker.name}</h2>
            <span className="role">{(activeSpeaker.role || 'NARRATOR').toUpperCase()}</span>
          </div>
          <div className="status">
            <i />
            <span id="st">{isPlaying ? 'Speaking' : isPaused ? 'Paused' : 'Idle'}</span>
          </div>
        </div>

        {/* Fixed-Height Glass Play Card with Scrollable Lines (flex: 1 1 auto) */}
        <div className="play-card">
          <div className="ph">
            <span>Theatrical screenplay</span>
            <span>{lines.length > 0 ? `${lines.length} lines directed` : 'Ready to direct'}</span>
          </div>

          <div
            className="lines"
            ref={linesContainerRef}
            id="teleprompter-list"
            tabIndex={0}
            onWheel={handleUserScrollInteraction}
            onTouchStart={handleUserScrollInteraction}
            onPointerDown={handleUserScrollInteraction}
            onKeyDown={(e) => {
              if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(e.key)) {
                handleUserScrollInteraction();
              }
            }}
            onScroll={() => {
              if (Date.now() - lastProgrammaticScrollRef.current > 800) {
                if (followingRef.current) {
                  followingRef.current = false;
                  setFollowing(false);
                }
              }
            }}
          >
            {lines.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--dim)', font: '400 13px var(--mono)' }}>
                No live screenplay streaming yet.<br />
                Press <strong style={{ color: 'var(--text)' }}>Play</strong> on the dock below to direct Chapter {selectedChapter} in real-time.
              </div>
            ) : (
              lines.map((line) => {
                const isOn = line.line_index === activeLineIndex;
                const charColor = getCharacterColor(line.character_name || line.speaker);
                return (
                  <div
                    key={line.line_index}
                    id={`script-line-${line.line_index}`}
                    className={`line ${isOn ? 'on' : ''}`}
                    style={{ '--c': charColor } as React.CSSProperties}
                    onClick={() => handleLineClick(line.line_index)}
                  >
                    <div className="meta">
                      <span className="who-l">{line.character_name || line.speaker}</span>
                    </div>
                    <p>{line.text}</p>
                  </div>
                );
              })
            )}
          </div>

          {/* Jump to Live Button */}
          {!following && lines.length > 0 && (
            <button
              className="jump-live-btn"
              onClick={handleJumpToLive}
            >
              <span className="live-dot" />
              Jump to live
            </button>
          )}
        </div>

        {/* =========================================================================
            3. MASTER TRANSPORT DOCK (Centered, Relative, flex: none)
        ========================================================================= */}
        <div className="dock">
          <button
            className="play-btn"
            id="pb"
            aria-label={isPlaying ? 'Pause' : 'Play'}
            onClick={() => {
              if (isPlaying) {
                pauseDramaStream();
              } else if (isPaused) {
                resumeDramaStream();
              } else {
                startDramaStream();
              }
            }}
          >
            <svg viewBox="0 0 24 24" id="ic">
              <path d={isPlaying ? 'M6 4h4v16H6zM14 4h4v16h-4z' : 'M7 4.5v15l13-7.5z'} />
            </svg>
          </button>

          <button className="sq" aria-label="Stop" id="sb" onClick={stopDramaStream}>
            <i />
          </button>

          <div className="seg">
            <button
              className={activeScope === 'chapter' ? 'on' : ''}
              onClick={() => {
                if (activeScope !== 'chapter') {
                  stopDramaStream();
                  setActiveScope('chapter');
                  followingRef.current = true;
                  setFollowing(true);
                }
              }}
            >
              Full chapter
            </button>
            <button
              className={activeScope === 'scene' ? 'on' : ''}
              onClick={() => {
                if (activeScope !== 'scene') {
                  stopDramaStream();
                  setActiveScope('scene');
                  followingRef.current = true;
                  setFollowing(true);
                }
              }}
            >
              1 scene
            </button>
          </div>

          <div className="prog">
            <div className="t">
              <span id="rd">
                {isPlaying ? 'Playing' : isPaused ? 'Paused' : streamingStatus}
              </span>
              <span>
                {lines.length > 0
                  ? `${lines.length} lines · ${bufferedSec.toFixed(1)}s`
                  : bufferedCount > 0
                  ? `${bufferedCount} lines · ${bufferedSec.toFixed(1)}s`
                  : '24kHz'}
              </span>
            </div>
            <div className="track" style={{ cursor: 'default' }}>
              <div
                className="fill"
                id="fl"
                style={{
                  width:
                    lines.length > 0
                      ? `${Math.min(100, Math.max(0, (activeLineIndex / lines.length) * 100))}%`
                      : '0%',
                }}
              />
            </div>
          </div>

          <div className="vol">
            <svg viewBox="0 0 24 24">
              <path d="M4 9v6h4l5 4V5L8 9zM16 8.5a5 5 0 010 7" />
            </svg>
            <div
              className="track"
              onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const newVol = Math.max(0, Math.min(1, clickX / rect.width));
                setVolume(newVol);
                audioEngine.setVolume(newVol);
              }}
            >
              <div className="fill" style={{ width: `${volume * 100}%` }} />
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          4. RIGHT AUDITION & CASTING SUITE DRAWER (Glass Themed)
      ========================================================================= */}
      {castingDrawerOpen && (
        <aside className="casting-drawer">
          <div className="casting-header">
            <h3>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 00-3-3.87" />
                <path d="M16 3.13a4 4 0 010 7.75" />
              </svg>
              Casting & Audition Suite
            </h3>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="btn"
                onClick={saveCastSheet}
                disabled={isSavingCast}
                style={{ padding: '4px 12px', fontSize: '11px', fontFamily: 'var(--mono)' }}
              >
                {isSavingCast ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={() => setCastingDrawerOpen(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--muted)',
                  cursor: 'pointer',
                  fontSize: '16px',
                  padding: '0 4px',
                }}
              >
                ✕
              </button>
            </div>
          </div>

          <div className="casting-body">
            <div style={{ fontSize: '12px', color: 'var(--dim)', lineHeight: 1.5 }}>
              Audition and cast characters from the 26 Kokoro neural voices. Each preview sample is synthesized at 24kHz.
            </div>

            {!castSheet || Object.keys(castSheet.characters).length === 0 ? (
              <div style={{ font: '400 12px var(--mono)', color: 'var(--dim)', textAlign: 'center', padding: '24px 0' }}>
                No cast sheet loaded for this book yet.
              </div>
            ) : (
              Object.entries(castSheet.characters).map(([cid, char]) => (
                <div key={cid} className="cast-card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <b style={{ color: 'var(--text)', fontSize: '13px' }}>{char.name}</b>
                    <span className="role">{char.role}</span>
                  </div>
                  <div>
                    <label style={{ display: 'block', font: '500 10px var(--mono)', color: 'var(--dim)', textTransform: 'uppercase', marginBottom: '4px' }}>
                      Assigned Voice
                    </label>
                    <select
                      value={char.voice_id}
                      onChange={(e) => {
                        const newVoice = e.target.value;
                        setCastSheet((prev) => {
                          if (!prev) return null;
                          return {
                            ...prev,
                            characters: {
                              ...prev.characters,
                              [cid]: { ...char, voice_id: newVoice },
                            },
                          };
                        });
                      }}
                    >
                      {voices.map((v) => (
                        <option key={v.voice_id} value={v.voice_id}>
                          {v.voice_id} · {v.name} ({v.gender}, {v.accent})
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    className="audition-btn"
                    onClick={() => auditionVoice(char.voice_id)}
                    disabled={auditioningVoiceId === char.voice_id}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M7 4.5v15l13-7.5z" />
                    </svg>
                    <span>
                      {auditioningVoiceId === char.voice_id ? 'Auditioning 24kHz...' : 'Audition 24kHz Sample'}
                    </span>
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
