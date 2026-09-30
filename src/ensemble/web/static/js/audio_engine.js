/**
 * Ensemble Studio - Web Audio Engine
 * Handles low-latency streaming audio queue, AnalyserNode frequency visualization,
 * and seamless multi-cast line transitions using the Web Audio API.
 */

class StudioAudioEngine {
  constructor(canvasElement) {
    this.canvas = canvasElement;
    this.ctx = null;
    this.analyser = null;
    this.gainNode = null;
    this.isPlaying = false;
    this.isPaused = false;
    this.currentSource = null;

    // Queue of line items: { lineIndex, audioBuffer, metadata }
    this.queue = [];
    this.currentLineIndex = -1;
    this.playbackHistory = [];

    // Callbacks
    this.onLineStart = null;
    this.onLineEnd = null;
    this.onQueueEmpty = null;
    this.onPlaybackStateChange = null;

    // Canvas rendering loop
    this.animationFrameId = null;
    if (this.canvas) {
      this.initVisualizer();
    }
  }

  ensureContext() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AudioCtx();
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 128;
      this.analyser.smoothingTimeConstant = 0.8;

      this.gainNode = this.ctx.createGain();
      this.gainNode.gain.value = 1.0;

      this.gainNode.connect(this.analyser);
      this.analyser.connect(this.ctx.destination);
    }

    if (this.ctx.state === "suspended") {
      this.ctx.resume();
    }
  }

  setVolume(vol) {
    if (this.gainNode) {
      this.gainNode.gain.value = Math.max(0, Math.min(1, vol));
    }
  }

  async decodeBase64Wav(base64Str) {
    this.ensureContext();
    const binaryStr = atob(base64Str);
    const len = binaryStr.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryStr.charCodeAt(i);
    }
    return await this.ctx.decodeAudioData(bytes.buffer.slice(0));
  }

  async enqueueLine(lineData) {
    try {
      const audioBuffer = await this.decodeBase64Wav(lineData.audio_base64);
      this.queue.push({
        lineIndex: lineData.line_index,
        audioBuffer: audioBuffer,
        metadata: lineData,
      });

      // If we are currently in playback mode and not currently playing, start playing
      if (this.isPlaying && !this.currentSource && !this.isPaused) {
        this.playNext();
      }
    } catch (err) {
      console.error("Failed to decode audio line:", err);
    }
  }

  startPlayback() {
    this.ensureContext();
    this.isPlaying = true;
    this.isPaused = false;
    if (this.onPlaybackStateChange) this.onPlaybackStateChange(true);

    if (!this.currentSource) {
      this.playNext();
    }
  }

  playNext() {
    if (!this.isPlaying || this.isPaused) return;

    if (this.queue.length === 0) {
      this.currentSource = null;
      if (this.onQueueEmpty) this.onQueueEmpty();
      return;
    }

    const item = this.queue.shift();
    this.currentLineIndex = item.lineIndex;
    this.playbackHistory.push(item);

    const source = this.ctx.createBufferSource();
    source.buffer = item.audioBuffer;
    source.connect(this.gainNode);

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
        // Seamlessly step to the next buffered line
        this.playNext();
      }
    };

    source.start(0);
  }

  pause() {
    if (this.ctx && this.isPlaying) {
      this.ctx.suspend();
      this.isPaused = true;
      if (this.onPlaybackStateChange) this.onPlaybackStateChange(false);
    }
  }

  resume() {
    if (this.ctx && this.isPaused) {
      this.ctx.resume();
      this.isPaused = false;
      if (this.onPlaybackStateChange) this.onPlaybackStateChange(true);
    }
  }

  stop() {
    this.isPlaying = false;
    this.isPaused = false;
    this.queue = [];
    if (this.currentSource) {
      try {
        this.currentSource.stop();
      } catch (e) {}
      this.currentSource = null;
    }
    if (this.onPlaybackStateChange) this.onPlaybackStateChange(false);
  }

  clearQueue() {
    this.queue = [];
    this.playbackHistory = [];
  }

  // Voice Preview Engine (for the Casting Board)
  async playVoicePreview(url) {
    this.ensureContext();
    try {
      const resp = await fetch(url);
      const arrayBuffer = await resp.arrayBuffer();
      const audioBuffer = await this.ctx.decodeAudioData(arrayBuffer);

      const previewSource = this.ctx.createBufferSource();
      previewSource.buffer = audioBuffer;
      previewSource.connect(this.gainNode);
      previewSource.start(0);

      return new Promise((resolve) => {
        previewSource.onended = () => resolve(true);
      });
    } catch (err) {
      console.error("Voice preview failed:", err);
      throw err;
    }
  }

  // Frequency Spectrum / Oscilloscope Visualizer
  initVisualizer() {
    const canvas = this.canvas;
    const canvasCtx = canvas.getContext("2d");

    const render = () => {
      this.animationFrameId = requestAnimationFrame(render);

      const width = canvas.width;
      const height = canvas.height;

      canvasCtx.fillStyle = "#0d0d10";
      canvasCtx.fillRect(0, 0, width, height);

      if (!this.analyser || (!this.isPlaying && !this.currentSource)) {
        // Idle ambient subtle line
        canvasCtx.beginPath();
        canvasCtx.moveTo(0, height / 2);
        canvasCtx.lineTo(width, height / 2);
        canvasCtx.strokeStyle = "#27272a";
        canvasCtx.lineWidth = 2;
        canvasCtx.stroke();
        return;
      }

      const bufferLength = this.analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      this.analyser.getByteFrequencyData(dataArray);

      const barWidth = (width / bufferLength) * 2.5;
      let barHeight;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        barHeight = (dataArray[i] / 255.0) * height * 0.9;

        // Gradient from warm amber to vibrant gold
        const alpha = Math.max(0.2, dataArray[i] / 255.0);
        canvasCtx.fillStyle = `rgba(245, 158, 11, ${alpha})`;

        canvasCtx.fillRect(
          x,
          height - barHeight,
          Math.max(1, barWidth - 1),
          barHeight
        );

        x += barWidth + 1;
      }
    };

    render();
  }
}

window.StudioAudioEngine = StudioAudioEngine;
