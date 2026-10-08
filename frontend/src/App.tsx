import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Navbar } from './components/Navbar';
import { VoiceOrb } from './components/VoiceOrb';
import { ScreenplayReader } from './components/ScreenplayReader';
import { BottomPlayerDock } from './components/BottomPlayerDock';
import { CastingDrawer } from './components/CastingDrawer';
import { LibraryView } from './components/LibraryView';
import { StudioAudioEngine, type LineMetadata } from './lib/audioEngine';

interface Book {
  filename: string;
  title: string;
  format: string;
}

interface Chapter {
  index: number;
  title: string;
  scene_count: number;
}

interface Voice {
  voice_id: string;
  name: string;
  gender: string;
  accent: string;
  timbre: string;
}

interface CharacterProfile {
  name: string;
  role: string;
  gender: string;
  age_group: string;
  voice_id: string;
  personality_traits: string[];
}

interface CastSheet {
  book_title: string;
  narrator_id: string;
  characters: Record<string, CharacterProfile>;
}

export function App() {
  const [activeTab, setActiveTab] = useState<'stage' | 'casting' | 'library'>('stage');

  // Book & Chapter State
  const [books, setBooks] = useState<Book[]>([]);
  const [currentBook, setCurrentBook] = useState<string | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [currentChapter, setCurrentChapter] = useState<Chapter | null>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [castSheet, setCastSheet] = useState<CastSheet | null>(null);

  // Playback & Streaming State
  const [isStreaming, setIsStreaming] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [scope, setScope] = useState<number>(0); // 0 = Full Chapter, 1 = 1 Scene
  const [volume, setVolume] = useState<number>(1.0);
  const [streamingStatus, setStreamingStatus] = useState<string>('Ready');
  const [statusColor, setStatusColor] = useState<'amber' | 'green' | 'red' | 'zinc'>('zinc');
  const [toastError, setToastError] = useState<string | null>(null);

  // Active Speaker & Real-time Energy
  const [activeSpeaker, setActiveSpeaker] = useState<{
    name: string;
    voiceId: string;
    emotion: string;
    speed: number;
  }>({
    name: 'Narrator',
    voiceId: 'bm_george',
    emotion: 'reflective',
    speed: 1.0,
  });
  const [audioEnergy, setAudioEnergy] = useState<number>(0.0);

  // Screenplay & Buffer State
  const [lines, setLines] = useState<LineMetadata[]>([]);
  const [activeLineIndex, setActiveLineIndex] = useState<number>(0);
  const [totalLines, setTotalLines] = useState<number>(0);
  const [bufferedSec, setBufferedSec] = useState<number>(0);
  const [bufferedCount, setBufferedCount] = useState<number>(0);

  const socketRef = useRef<WebSocket | null>(null);
  const audioEngine = useMemo(() => new StudioAudioEngine(), []);

  // Update buffer badge
  const updateBufferMetrics = useCallback(() => {
    const total = audioEngine.queue.reduce((acc, it) => acc + it.audioBuffer.duration, 0);
    const count = audioEngine.queue.length;
    setBufferedSec(total);
    setBufferedCount(count);
  }, [audioEngine]);

  const isStreamingRef = useRef(isStreaming);
  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);

  // Audio Engine Event Listeners - Mounted once for application lifecycle
  useEffect(() => {
    audioEngine.onEnergyChange = (energy) => {
      setAudioEnergy(energy);
    };

    audioEngine.onBufferProgress = (count, target, totalSec) => {
      setBufferedSec(totalSec);
      setBufferedCount(count);
      if (isStreamingRef.current && audioEngine.isBuffering) {
        setStreamingStatus(`Buffering (${count}/${target} lines, ${totalSec.toFixed(1)}s)...`);
        setStatusColor('amber');
      }
    };

    audioEngine.onLineStart = (meta) => {
      setActiveLineIndex(meta.line_index);
      setActiveSpeaker({
        name: meta.character_name || meta.speaker,
        voiceId: meta.voice_id || 'bm_george',
        emotion: meta.emotion || 'natural',
        speed: meta.speed || 1.0,
      });
      updateBufferMetrics();
    };

    audioEngine.onLineEnd = () => {
      updateBufferMetrics();
    };

    audioEngine.onQueueEmpty = () => {
      if (audioEngine.isStreamComplete) {
        setStreamingStatus('Chapter Complete');
        setStatusColor('green');
        setIsPlaying(false);
        setIsPaused(false);
      } else if (!isStreamingRef.current) {
        setStreamingStatus('Ready');
        setStatusColor('zinc');
      }
    };

    audioEngine.onPlaybackStateChange = (playing) => {
      setIsPlaying(playing);
      setIsPaused(!playing && (audioEngine.queue.length > 0 || isStreamingRef.current || audioEngine.currentLineIndex > 0));
    };

    return () => {
      audioEngine.destroy();
    };
  }, [audioEngine, updateBufferMetrics]);

  // Initial Data Fetch
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        const [booksRes, voicesRes] = await Promise.all([
          fetch('/api/books').then((r) => r.json()),
          fetch('/api/voices').then((r) => r.json()),
        ]);

        const fetchedBooks = booksRes.books || [];
        setBooks(fetchedBooks);
        setVoices(voicesRes.voices || []);

        if (fetchedBooks.length > 0) {
          const firstBook = fetchedBooks[0].filename;
          setCurrentBook(firstBook);
          await loadBookChapters(firstBook);
          await loadCast(firstBook);
        }
      } catch (err) {
        console.error('Failed to load initial data:', err);
      }
    };

    loadInitialData();
  }, []);

  const loadBookChapters = async (filename: string) => {
    try {
      const resp = await fetch(`/api/books/${filename}/chapters`);
      const data = await resp.json();
      const chs: Chapter[] = data.chapters || [];
      setChapters(chs);
      if (chs.length > 0) {
        setCurrentChapter(chs[0]);
      }
    } catch (err) {
      console.error('Failed to load chapters:', err);
    }
  };

  const loadCast = async (filename: string) => {
    try {
      const resp = await fetch(`/api/books/${filename}/cast`);
      const data = await resp.json();
      setCastSheet(data);
    } catch (err) {
      console.error('Failed to load cast:', err);
    }
  };

  const handleBookChange = async (filename: string) => {
    setCurrentBook(filename);
    await loadBookChapters(filename);
    await loadCast(filename);
  };

  const handleChapterChange = (chapterIndex: number) => {
    const ch = chapters.find((c) => c.index === chapterIndex);
    if (ch) {
      setCurrentChapter(ch);
    }
  };

  const handleVolumeChange = (vol: number) => {
    setVolume(vol);
    audioEngine.setVolume(vol);
  };

  // Live WebSocket Streaming
  const startStream = () => {
    if (isStreaming || !currentBook || !currentChapter) return;

    audioEngine.ensureContext();
    audioEngine.clearQueue();
    audioEngine.stop();
    audioEngine.setStreamComplete(false);
    setLines([]);
    setActiveLineIndex(0);
    setTotalLines(0);

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/stream/${currentBook}`;
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      setIsStreaming(true);
      setIsPlaying(true);
      setIsPaused(false);
      setStreamingStatus('Directing screenplay...');
      setStatusColor('amber');

      ws.send(
        JSON.stringify({
          action: 'start',
          chapter: currentChapter.index,
          scenes: scope,
        })
      );
    };

    ws.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);

        if (msg.type === 'scene_start') {
          setStreamingStatus(`Directing scene ${msg.current_scene_number}/${msg.total_scenes}...`);
          setStatusColor('amber');
        } else if (msg.type === 'screenplay_ready' || msg.type === 'scene_script') {
          setLines((prev) => {
            const baseIndex = prev.length;
            const newLines: LineMetadata[] = (msg.lines || []).map((l: any, i: number) => ({
              ...l,
              line_index: l.line_index !== undefined ? l.line_index : (baseIndex + i + 1),
              total_lines: msg.total_lines || (msg.lines ? msg.lines.length : 0),
            }));
            return [...prev, ...newLines];
          });
          setTotalLines((prev) => prev + (msg.lines ? msg.lines.length : 0));
          setStreamingStatus('Synthesizing Kokoro ONNX (GPU)...');
          setStatusColor('amber');
        } else if (msg.type === 'line_audio') {
          const lineData: LineMetadata = msg.line || msg;
          await audioEngine.enqueueLine(lineData);

          if (!audioEngine.isPlaying && !audioEngine.isBuffering) {
            audioEngine.startPlayback();
            setStreamingStatus('Live Streaming (GPU)');
            setStatusColor('green');
          }
        } else if (msg.type === 'finished' || msg.type === 'chapter_complete') {
          setIsStreaming(false);
          audioEngine.setStreamComplete(true);
          if (audioEngine.isPlaying && audioEngine.queue.length > 0) {
            setStreamingStatus('Fully Buffered • Playing Audio');
            setStatusColor('green');
          } else if (!audioEngine.isPlaying) {
            setStreamingStatus('Chapter Complete');
            setStatusColor('green');
          }
        } else if (msg.type === 'error') {
          console.error('Stream error:', msg.message);
          setStreamingStatus('Director Paused');
          setStatusColor('red');
          setIsStreaming(false);
          setToastError(msg.message || 'The AI Director experienced a temporary issue.');
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      setStreamingStatus('Offline');
      setStatusColor('red');
      setIsStreaming(false);
      setToastError('Lost connection to audio streaming server. Please ensure the backend is running.');
    };

    ws.onclose = () => {
      setIsStreaming(false);
      socketRef.current = null;
    };
  };

  const pauseStream = async () => {
    await audioEngine.pause();
    setIsPaused(true);
    setIsPlaying(false);
    setStreamingStatus('Paused');
    setStatusColor('amber');
  };

  const resumeStream = async () => {
    await audioEngine.resume();
    setIsPaused(false);
    setIsPlaying(true);
    setStreamingStatus('Live Streaming (GPU)');
    setStatusColor('green');
  };

  const stopStream = () => {
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
    audioEngine.stop();
    setIsStreaming(false);
    setIsPlaying(false);
    setIsPaused(false);
    setStreamingStatus('Stopped');
    setStatusColor('zinc');
  };

  const handleSaveCast = async (updatedSheet: CastSheet) => {
    if (!currentBook) return;
    const resp = await fetch(`/api/books/${currentBook}/cast`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updatedSheet),
    });
    if (!resp.ok) {
      throw new Error('Failed to save cast');
    }
    setCastSheet(updatedSheet);
  };

  return (
    <div className="min-h-[100dvh] flex flex-col bg-[#070709] text-zinc-100">
      {/* Top Navbar */}
      <Navbar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        books={books}
        currentBook={currentBook}
        onBookChange={handleBookChange}
        chapters={chapters}
        currentChapter={currentChapter}
        onChapterChange={handleChapterChange}
        streamingStatus={streamingStatus}
        statusColor={statusColor}
      />

      {/* Floating Elegant Toast Notification for Provider Errors */}
      {toastError && (
        <div className="fixed top-16 right-6 z-50 max-w-sm bg-[#121218]/95 border border-red-500/30 rounded-xl p-3.5 shadow-2xl backdrop-blur-xl flex items-start space-x-3 text-xs animate-in fade-in slide-in-from-top-2">
          <div className="w-2 h-2 rounded-full bg-red-400 mt-1 flex-shrink-0 animate-pulse" />
          <div className="flex-1 space-y-1">
            <p className="font-semibold text-zinc-200">Director Notice</p>
            <p className="text-zinc-400 font-mono text-[11px] leading-relaxed">{toastError}</p>
          </div>
          <button
            onClick={() => setToastError(null)}
            className="text-zinc-500 hover:text-zinc-300 font-mono text-xs px-1.5 py-0.5 rounded hover:bg-white/[0.05]"
          >
            ✕
          </button>
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col pt-4">
        {activeTab === 'stage' && (
          <div className="flex-1 flex flex-col max-w-5xl mx-auto w-full px-4">
            {/* Living Voice Orb */}
            <VoiceOrb
              speakerName={activeSpeaker.name}
              voiceId={activeSpeaker.voiceId}
              emotion={activeSpeaker.emotion}
              energy={audioEnergy}
              isPlaying={!isPaused && (isStreaming || audioEngine.isPlaying)}
            />

            {/* Editorial Screenplay Reader */}
            <ScreenplayReader
              lines={lines}
              activeLineIndex={activeLineIndex}
            />

            {/* Floating Bottom Player Dock */}
            <BottomPlayerDock
              isStreaming={isStreaming}
              isPlaying={isPlaying || audioEngine.isPlaying}
              isPaused={isPaused}
              onStart={startStream}
              onPause={pauseStream}
              onResume={resumeStream}
              onStop={stopStream}
              activeSpeakerName={activeSpeaker.name}
              activeVoiceId={activeSpeaker.voiceId}
              currentLine={activeLineIndex}
              totalLines={totalLines}
              bufferedSec={bufferedSec}
              bufferedCount={bufferedCount}
              scope={scope}
              onScopeChange={setScope}
              volume={volume}
              onVolumeChange={handleVolumeChange}
            />
          </div>
        )}

        {activeTab === 'casting' && (
          <div className="p-6">
            <CastingDrawer
              castSheet={castSheet}
              voices={voices}
              audioEngine={audioEngine}
              onSaveCast={handleSaveCast}
            />
          </div>
        )}

        {activeTab === 'library' && (
          <div className="p-6">
            <LibraryView />
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
