export interface LineMetadata {
  line_index: number;
  total_lines?: number;
  scene_line_index?: number;
  speaker: string;
  character_name: string;
  emotion?: string;
  voice_id?: string;
  speed?: number;
  pause_after_ms?: number;
  duration_ms?: number;
  text: string;
  scene_index?: number;
  audio_base64: string;
}

export interface QueueItem {
  lineIndex: number;
  audioBuffer: AudioBuffer;
  metadata: LineMetadata;
}

export interface AudioFrequencyData {
  energy: number;   // 0.0 - 1.0 overall volume
  bass: number;     // 0.0 - 1.0 low-end
  mid: number;      // 0.0 - 1.0 voice presence
  treble: number;   // 0.0 - 1.0 air & brightness
}

export class StudioAudioEngine {
  ctx: AudioContext | null = null;
  analyser: AnalyserNode | null = null;
  gainNode: GainNode | null = null;

  isPlaying = false;
  isPaused = false;
  currentSource: AudioBufferSourceNode | null = null;

  queue: QueueItem[] = [];
  currentLineIndex = -1;
  playbackHistory: QueueItem[] = [];

  // Jitter buffer settings (Kokoro generation needs ~3s runway for seamless play)
  minBufferLines = 2;
  minBufferSec = 3.5;
  isBuffering = true;
  isStreamComplete = false;

  // Real-time audio frequency telemetry
  currentFreq: AudioFrequencyData = { energy: 0, bass: 0, mid: 0, treble: 0 };

  // Callbacks
  onLineStart?: (meta: LineMetadata, duration: number) => void;
  onLineEnd?: (meta: LineMetadata) => void;
  onQueueEmpty?: () => void;
  onBufferProgress?: (count: number, target: number, totalSec: number) => void;
  onPlaybackStateChange?: (playing: boolean) => void;
  onFrequencyChange?: (freq: AudioFrequencyData) => void;

  private animationFrameId: number | null = null;

  constructor() {
    this.startFrequencyLoop();
  }

  ensureContext() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.ctx = new AudioCtx();
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 128;
      this.analyser.smoothingTimeConstant = 0.8;

      this.gainNode = this.ctx.createGain();
      this.gainNode.gain.value = 1.0;

      this.gainNode.connect(this.analyser);
      this.analyser.connect(this.ctx.destination);
    }

    if (this.ctx.state === 'suspended') {
      this.ctx.resume().catch((e) => console.warn('AudioContext resume failed:', e));
    }

    this.startFrequencyLoop();
  }

  setVolume(vol: number) {
    if (this.gainNode) {
      this.gainNode.gain.value = Math.max(0, Math.min(1, vol));
    }
  }

  async decodeBase64Wav(base64Str: string): Promise<AudioBuffer> {
    this.ensureContext();
    const binaryStr = atob(base64Str);
    const len = binaryStr.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryStr.charCodeAt(i);
    }
    return await this.ctx!.decodeAudioData(bytes.buffer.slice(0));
  }

  async enqueueLine(lineData: LineMetadata) {
    try {
      // Deduplicate: Don't enqueue if already queued or played
      if (
        this.queue.some((it) => it.lineIndex === lineData.line_index) ||
        this.playbackHistory.some((it) => it.lineIndex === lineData.line_index)
      ) {
        return;
      }

      const audioBuffer = await this.decodeBase64Wav(lineData.audio_base64);
      this.queue.push({
        lineIndex: lineData.line_index,
        audioBuffer,
        metadata: lineData,
      });

      const totalBufferedSec = this.queue.reduce((acc, it) => acc + it.audioBuffer.duration, 0);

      if (this.isBuffering) {
        if (this.onBufferProgress) {
          this.onBufferProgress(this.queue.length, this.minBufferLines, totalBufferedSec);
        }

        if (this.queue.length >= this.minBufferLines || totalBufferedSec >= this.minBufferSec) {
          this.isBuffering = false;
          if (this.isPlaying && !this.currentSource && !this.isPaused) {
            this.playNext();
          }
        }
      } else {
        if (this.isPlaying && !this.currentSource && !this.isPaused) {
          this.playNext();
        }
      }
    } catch (err) {
      console.error('Failed to decode line audio:', err);
    }
  }

  startPlayback() {
    this.ensureContext();
    this.isPlaying = true;
    this.isPaused = false;
    if (this.onPlaybackStateChange) this.onPlaybackStateChange(true);

    const totalBufferedSec = this.queue.reduce((acc, it) => acc + it.audioBuffer.duration, 0);
    if (this.queue.length >= this.minBufferLines || totalBufferedSec >= this.minBufferSec) {
      this.isBuffering = false;
      if (!this.currentSource) {
        this.playNext();
      }
    } else {
      this.isBuffering = true;
      if (this.onBufferProgress) {
        this.onBufferProgress(this.queue.length, this.minBufferLines, totalBufferedSec);
      }
    }
  }

  playNext() {
    if (!this.isPlaying || this.isPaused) return;

    if (this.queue.length === 0) {
      this.currentSource = null;
      if (this.isStreamComplete) {
        this.isPlaying = false;
        this.isBuffering = false;
        if (this.onPlaybackStateChange) this.onPlaybackStateChange(false);
      } else {
        this.isBuffering = true;
      }
      if (this.onQueueEmpty) this.onQueueEmpty();
      return;
    }

    const item = this.queue.shift()!;
    this.currentLineIndex = item.lineIndex;
    this.playbackHistory.push(item);

    // Guard against corrupted/zero-length audio buffers
    if (!item.audioBuffer || item.audioBuffer.duration <= 0.02) {
      console.warn(`[AudioEngine] Skipping zero-duration buffer for line ${item.lineIndex}`);
      setTimeout(() => this.playNext(), 50);
      return;
    }

    this.ensureContext();
    const source = this.ctx!.createBufferSource();
    source.buffer = item.audioBuffer;
    source.connect(this.gainNode!);

    this.currentSource = source;

    if (this.onLineStart) {
      this.onLineStart(item.metadata, item.audioBuffer.duration);
    }

    source.onended = () => {
      if (this.currentSource === source) {
        this.currentSource = null;
        if (this.onLineEnd) {
          this.onLineEnd(item.metadata);
        }
        this.playNext();
      }
    };

    source.start(0);
  }

  setStreamComplete(complete: boolean = true) {
    this.isStreamComplete = complete;
    if (complete && !this.currentSource && this.queue.length === 0) {
      this.isPlaying = false;
      this.isBuffering = false;
      if (this.onPlaybackStateChange) this.onPlaybackStateChange(false);
      if (this.onQueueEmpty) this.onQueueEmpty();
    }
  }

  async pause() {
    this.isPaused = true;
    if (this.ctx && this.ctx.state === 'running') {
      try {
        await this.ctx.suspend();
      } catch (e) {
        console.error('AudioContext suspend failed:', e);
      }
    }
    if (this.onPlaybackStateChange) this.onPlaybackStateChange(false);
  }

  async resume() {
    this.ensureContext();
    this.isPaused = false;
    this.isPlaying = true;
    if (this.ctx && this.ctx.state === 'suspended') {
      try {
        await this.ctx.resume();
      } catch (e) {
        console.error('AudioContext resume failed:', e);
      }
    }
    if (this.onPlaybackStateChange) this.onPlaybackStateChange(true);

    if (!this.currentSource && this.queue.length > 0) {
      this.playNext();
    }
  }

  stop() {
    this.isPlaying = false;
    this.isPaused = false;
    this.isStreamComplete = false;
    this.queue = [];
    if (this.currentSource) {
      try {
        this.currentSource.stop();
      } catch {
        // Ignored
      }
      this.currentSource = null;
    }
    if (this.onPlaybackStateChange) this.onPlaybackStateChange(false);
  }

  clearQueue() {
    this.queue = [];
    this.playbackHistory = [];
    this.isStreamComplete = false;
  }

  async playVoicePreview(url: string): Promise<boolean> {
    this.ensureContext();
    this.stop(); // Stop ongoing stream preview
    const resp = await fetch(url);
    const arrayBuffer = await resp.arrayBuffer();
    const audioBuffer = await this.ctx!.decodeAudioData(arrayBuffer);

    const previewSource = this.ctx!.createBufferSource();
    previewSource.buffer = audioBuffer;
    previewSource.connect(this.gainNode!);

    this.currentSource = previewSource;
    this.isPlaying = true;
    if (this.onPlaybackStateChange) this.onPlaybackStateChange(true);

    return new Promise((resolve) => {
      previewSource.onended = () => {
        if (this.currentSource === previewSource) {
          this.currentSource = null;
          this.isPlaying = false;
          if (this.onPlaybackStateChange) this.onPlaybackStateChange(false);
        }
        resolve(true);
      };
      previewSource.start(0);
    });
  }

  startFrequencyLoop() {
    if (this.animationFrameId !== null) return;

    const loop = () => {
      this.animationFrameId = requestAnimationFrame(loop);

      if (!this.analyser || !this.isPlaying || this.isPaused || !this.currentSource) {
        this.currentFreq = { energy: 0, bass: 0, mid: 0, treble: 0 };
        if (this.onFrequencyChange) this.onFrequencyChange(this.currentFreq);
        return;
      }

      const binCount = this.analyser.frequencyBinCount;
      const dataArray = new Uint8Array(binCount);
      this.analyser.getByteFrequencyData(dataArray);

      // Split into frequency ranges
      // binCount is typically 64 bins (0 to Nyquist)
      const bassBins = Math.floor(binCount * 0.2);
      const midBins = Math.floor(binCount * 0.6);

      let sumTotal = 0;
      let sumBass = 0;
      let sumMid = 0;
      let sumTreble = 0;

      for (let i = 0; i < binCount; i++) {
        const val = dataArray[i];
        sumTotal += val;
        if (i < bassBins) {
          sumBass += val;
        } else if (i < midBins) {
          sumMid += val;
        } else {
          sumTreble += val;
        }
      }

      const avgTotal = sumTotal / (binCount * 255.0);
      const avgBass = sumBass / (Math.max(1, bassBins) * 255.0);
      const avgMid = sumMid / (Math.max(1, midBins - bassBins) * 255.0);
      const avgTreble = sumTreble / (Math.max(1, binCount - midBins) * 255.0);

      this.currentFreq = {
        energy: Math.min(1.0, avgTotal * 2.2),
        bass: Math.min(1.0, avgBass * 2.0),
        mid: Math.min(1.0, avgMid * 2.2),
        treble: Math.min(1.0, avgTreble * 2.5),
      };

      if (this.onFrequencyChange) {
        this.onFrequencyChange(this.currentFreq);
      }
    };

    loop();
  }

  destroy() {
    if (this.animationFrameId !== null) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
    this.stop();
  }
}
