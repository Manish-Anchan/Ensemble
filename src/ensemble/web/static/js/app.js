/**
 * Ensemble Studio - Primary Application Logic
 */

document.addEventListener("DOMContentLoaded", () => {
  // App State
  const state = {
    books: [],
    currentBook: null,
    chapters: [],
    currentChapter: null,
    voices: [],
    castSheet: null,
    socket: null,
    isStreaming: false,
    activeTab: "player",
    totalLinesInScene: 0,
    currentLineIndex: 0,
  };

  // UI Elements
  const bookSelect = document.getElementById("book-select");
  const chapterSelect = document.getElementById("chapter-select");
  const sceneCountBadge = document.getElementById("scene-count-badge");
  const btnStartStream = document.getElementById("btn-start-stream");
  const btnPauseStream = document.getElementById("btn-pause-stream");
  const btnStopStream = document.getElementById("btn-stop-stream");
  const streamStatusBadge = document.getElementById("stream-status-badge");
  const activeSpeakerName = document.getElementById("active-speaker-name");
  const activeSpeakerVoice = document.getElementById("active-speaker-voice");
  const activeSpeakerEmotion = document.getElementById("active-speaker-emotion");
  const activeSpeakerSpeed = document.getElementById("active-speaker-speed");
  const activeSpeakerAvatar = document.getElementById("active-speaker-avatar");
  const teleprompterList = document.getElementById("teleprompter-list");
  const visualizerCanvas = document.getElementById("visualizer-canvas");
  const streamProgressFill = document.getElementById("stream-progress-fill");
  const lineCounterText = document.getElementById("line-counter-text");
  const castGrid = document.getElementById("cast-grid");
  const btnSaveCast = document.getElementById("btn-save-cast");
  const outputsTableBody = document.getElementById("outputs-table-body");
  const volumeSlider = document.getElementById("volume-slider");
  const scenesSelect = document.getElementById("scenes-select");

  // Audio Engine
  const audioEngine = new window.StudioAudioEngine(visualizerCanvas);

  if (volumeSlider) {
    volumeSlider.addEventListener("input", (e) => {
      audioEngine.setVolume(parseFloat(e.target.value));
    });
  }

  // Audio Engine Callbacks
  audioEngine.onLineStart = (meta, duration) => {
    state.currentLineIndex = meta.line_index;
    updateActiveSpeakerUI(meta);
    highlightTeleprompterLine(meta.line_index);
    updateProgressUI(meta.line_index, meta.total_lines);
  };

  audioEngine.onLineEnd = (meta) => {
    const lineEl = document.getElementById(`line-item-${meta.line_index}`);
    if (lineEl) {
      lineEl.classList.remove("is-active");
      lineEl.classList.add("is-passed");
    }
  };

  audioEngine.onQueueEmpty = () => {
    if (!state.isStreaming) {
      setStreamingStatus("Ready", "zinc");
    }
  };

  audioEngine.onPlaybackStateChange = (playing) => {
    if (playing) {
      btnPauseStream.textContent = "Pause";
    } else {
      btnPauseStream.textContent = "Resume";
    }
  };

  // --------------------------------------------------------------------------
  // Navigation Tabs
  // --------------------------------------------------------------------------
  const tabButtons = document.querySelectorAll("[data-tab-target]");
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-tab-target");
      switchTab(target);
    });
  });

  function switchTab(tabId) {
    state.activeTab = tabId;
    tabButtons.forEach((b) => {
      const active = b.getAttribute("data-tab-target") === tabId;
      b.classList.toggle("text-amber-400", active);
      b.classList.toggle("border-b-2", active);
      b.classList.toggle("border-amber-400", active);
      b.classList.toggle("text-zinc-400", !active);
    });

    document.querySelectorAll(".tab-pane").forEach((pane) => {
      pane.classList.toggle("active", pane.id === `tab-${tabId}`);
    });

    if (tabId === "casting") {
      loadCastBoard();
    } else if (tabId === "library") {
      loadOutputs();
    }
  }

  // --------------------------------------------------------------------------
  // Books & Chapters Loading
  // --------------------------------------------------------------------------
  async function loadBooks() {
    try {
      const resp = await fetch("/api/books");
      const data = await resp.json();
      state.books = data.books || [];

      bookSelect.innerHTML = "";
      state.books.forEach((book, idx) => {
        const opt = document.createElement("option");
        opt.value = book.filename;
        opt.textContent = `${book.title} (${book.format.toUpperCase()})`;
        bookSelect.appendChild(opt);
      });

      if (state.books.length > 0) {
        state.currentBook = state.books[0].filename;
        await loadBookDetails(state.currentBook);
      }
    } catch (err) {
      console.error("Failed to load books:", err);
    }
  }

  bookSelect.addEventListener("change", async (e) => {
    state.currentBook = e.target.value;
    await loadBookDetails(state.currentBook);
  });

  async function loadBookDetails(filename) {
    try {
      setStreamingStatus("Loading book...", "zinc");
      const resp = await fetch(`/api/books/${filename}/chapters`);
      const data = await resp.json();
      state.chapters = data.chapters || [];

      chapterSelect.innerHTML = "";
      state.chapters.forEach((ch) => {
        const opt = document.createElement("option");
        opt.value = ch.index;
        opt.textContent = `Chapter ${ch.index}: ${ch.title} (${ch.scene_count} scenes)`;
        chapterSelect.appendChild(opt);
      });

      if (state.chapters.length > 0) {
        state.currentChapter = state.chapters[0];
        sceneCountBadge.textContent = `${state.currentChapter.scene_count} scenes`;
      }

      await loadCastSheet(filename);
      setStreamingStatus("Ready", "zinc");
    } catch (err) {
      console.error("Failed to load book chapters:", err);
      setStreamingStatus("Error loading chapters", "red");
    }
  }

  chapterSelect.addEventListener("change", (e) => {
    const chIdx = parseInt(e.target.value, 10);
    state.currentChapter = state.chapters.find((c) => c.index === chIdx) || state.chapters[0];
    if (state.currentChapter) {
      sceneCountBadge.textContent = `${state.currentChapter.scene_count} scenes`;
    }
  });

  // --------------------------------------------------------------------------
  // Voice Catalog
  // --------------------------------------------------------------------------
  async function loadVoices() {
    try {
      const resp = await fetch("/api/voices");
      const data = await resp.json();
      state.voices = data.voices || [];
    } catch (err) {
      console.error("Failed to load voice catalog:", err);
    }
  }

  // --------------------------------------------------------------------------
  // Live Streaming & WebSocket Execution
  // --------------------------------------------------------------------------
  btnStartStream.addEventListener("click", () => {
    if (state.isStreaming) return;
    startDramaStream();
  });

  btnPauseStream.addEventListener("click", () => {
    if (!state.isStreaming) return;
    if (audioEngine.isPaused) {
      audioEngine.resume();
    } else {
      audioEngine.pause();
    }
  });

  btnStopStream.addEventListener("click", () => {
    stopDramaStream();
  });

  function startDramaStream() {
    if (!state.currentBook || !state.currentChapter) return;

    audioEngine.ensureContext();
    audioEngine.clearQueue();
    audioEngine.stop();

    teleprompterList.innerHTML = `<div class="p-8 text-center text-zinc-500 font-mono text-sm animate-pulse">Connecting to live studio pipeline...</div>`;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/stream/${state.currentBook}`;

    state.socket = new WebSocket(wsUrl);
    state.isStreaming = true;

    btnStartStream.classList.add("hidden");
    btnPauseStream.classList.remove("hidden");
    btnStopStream.classList.remove("hidden");
    setStreamingStatus("Synthesizing Live", "amber");

    state.socket.onopen = () => {
      const maxScenes = parseInt(scenesSelect.value, 10) || 0;
      state.socket.send(
        JSON.stringify({
          action: "start",
          chapter: state.currentChapter.index,
          scenes: maxScenes,
        })
      );
    };

    state.socket.onmessage = async (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "started") {
        setStreamingStatus(`Chapter ${data.chapter_index} Started`, "amber");
      } else if (data.type === "scene_start") {
        setStreamingStatus(`Directing Scene ${data.current_scene_number}/${data.total_scenes}...`, "amber");
      } else if (data.type === "screenplay_ready") {
        renderScreenplayInTeleprompter(data.lines);
        state.totalLinesInScene = data.total_lines;
        setStreamingStatus("Performing & Synthesizing", "amber");
        audioEngine.startPlayback();
      } else if (data.type === "line_audio") {
        await audioEngine.enqueueLine(data);
      } else if (data.type === "scene_completed") {
        // Scene finished streaming
      } else if (data.type === "finished") {
        state.isStreaming = false;
        btnStartStream.classList.remove("hidden");
        btnPauseStream.classList.add("hidden");
        btnStopStream.classList.add("hidden");
        setStreamingStatus("Chapter Production Complete", "green");
      } else if (data.type === "error") {
        setStreamingStatus(`Error: ${data.message}`, "red");
        stopDramaStream();
      }
    };

    state.socket.onerror = (err) => {
      console.error("WebSocket error:", err);
      setStreamingStatus("Connection error", "red");
      stopDramaStream();
    };

    state.socket.onclose = () => {
      state.isStreaming = false;
    };
  }

  function stopDramaStream() {
    if (state.socket) {
      state.socket.close();
      state.socket = null;
    }
    state.isStreaming = false;
    audioEngine.stop();
    btnStartStream.classList.remove("hidden");
    btnPauseStream.classList.add("hidden");
    btnStopStream.classList.add("hidden");
    setStreamingStatus("Stopped", "zinc");
  }

  // --------------------------------------------------------------------------
  // Teleprompter & Active Speaker UI
  // --------------------------------------------------------------------------
  function renderScreenplayInTeleprompter(lines) {
    teleprompterList.innerHTML = "";
    lines.forEach((line, idx) => {
      const lineNum = idx + 1;
      const el = document.createElement("div");
      el.id = `line-item-${lineNum}`;
      el.className = "teleprompter-line p-4 rounded-lg studio-card-elevated is-upcoming cursor-pointer";

      // Speaker color tag
      const isNarrator = line.speaker.toLowerCase().includes("narrator");
      const tagColor = isNarrator ? "text-amber-400" : "text-sky-400";

      el.innerHTML = `
        <div class="flex items-center justify-between mb-1.5">
          <div class="flex items-center space-x-2">
            <span class="font-bold text-sm ${tagColor}">${line.character_name}</span>
            <span class="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 font-mono">${line.emotion}</span>
          </div>
          <span class="text-xs font-mono text-zinc-500">#${lineNum}</span>
        </div>
        <p class="text-zinc-200 text-base leading-relaxed font-sans">${escapeHtml(line.text)}</p>
      `;

      teleprompterList.appendChild(el);
    });
  }

  function highlightTeleprompterLine(lineIndex) {
    const el = document.getElementById(`line-item-${lineIndex}`);
    if (el) {
      document.querySelectorAll(".teleprompter-line.is-active").forEach((item) => {
        item.classList.remove("is-active");
        item.classList.add("is-passed");
      });
      el.classList.remove("is-upcoming", "is-passed");
      el.classList.add("is-active");

      // Auto-scroll
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function updateActiveSpeakerUI(meta) {
    activeSpeakerName.textContent = meta.character_name || meta.speaker;
    activeSpeakerVoice.textContent = meta.voice_id || "bm_george";
    activeSpeakerEmotion.textContent = `[${meta.emotion || "natural"}]`;
    activeSpeakerSpeed.textContent = `${meta.speed || 1.0}x`;

    // Dynamic Speaker Initial
    const name = meta.character_name || meta.speaker;
    activeSpeakerAvatar.textContent = name.charAt(0).toUpperCase();

    // Pulse active halo
    const halo = document.getElementById("speaker-halo-ring");
    if (halo) {
      halo.classList.add("is-active");
    }
  }

  function updateProgressUI(current, total) {
    const pct = total > 0 ? (current / total) * 100 : 0;
    streamProgressFill.style.width = `${pct}%`;
    lineCounterText.textContent = `Line ${current} of ${total}`;
  }

  function setStreamingStatus(text, color) {
    streamStatusBadge.textContent = text;
    streamStatusBadge.className = "text-xs font-mono font-medium px-2.5 py-1 rounded-full ";
    if (color === "amber") {
      streamStatusBadge.className += "bg-amber-950/80 text-amber-300 border border-amber-500/30 pulse-indicator";
    } else if (color === "green") {
      streamStatusBadge.className += "bg-emerald-950/80 text-emerald-300 border border-emerald-500/30";
    } else if (color === "red") {
      streamStatusBadge.className += "bg-red-950/80 text-red-300 border border-red-500/30";
    } else {
      streamStatusBadge.className += "bg-zinc-800 text-zinc-400 border border-zinc-700";
    }
  }

  // --------------------------------------------------------------------------
  // Casting Board
  // --------------------------------------------------------------------------
  async function loadCastSheet(filename) {
    try {
      const resp = await fetch(`/api/books/${filename}/cast`);
      state.castSheet = await resp.json();
    } catch (err) {
      console.error("Failed to load cast sheet:", err);
    }
  }

  async function loadCastBoard() {
    if (!state.currentBook) return;
    await loadCastSheet(state.currentBook);

    castGrid.innerHTML = "";
    if (!state.castSheet || !state.castSheet.characters || Object.keys(state.castSheet.characters).length === 0) {
      castGrid.innerHTML = `
        <div class="col-span-full p-12 text-center studio-card">
          <p class="text-zinc-400 mb-2">No cast sheet found for this book yet.</p>
          <p class="text-xs text-zinc-500 font-mono">Run live stream to auto-cast characters or generate from CLI.</p>
        </div>
      `;
      return;
    }

    Object.entries(state.castSheet.characters).forEach(([charId, char]) => {
      const card = document.createElement("div");
      card.className = "studio-card p-5 flex flex-col justify-between";
      card.setAttribute("data-char-id", charId);

      const isNarrator = charId === state.castSheet.narrator_id || char.role === "narrator";
      const roleColor = isNarrator ? "bg-amber-950 text-amber-300 border-amber-500/30" : "bg-zinc-800 text-zinc-300 border-zinc-700";

      // Build Voice Options Dropdown
      let voiceOptions = "";
      state.voices.forEach((v) => {
        const selected = v.voice_id === char.voice_id ? "selected" : "";
        voiceOptions += `<option value="${v.voice_id}" ${selected}>${v.name} (${v.accent.toUpperCase()} ${v.gender.toUpperCase()} • ${v.timbre})</option>`;
      });

      // Traits tags
      const traitsHtml = (char.personality_traits || [])
        .slice(0, 4)
        .map((t) => `<span class="text-xs bg-zinc-800/80 text-zinc-400 px-2 py-0.5 rounded font-mono">${escapeHtml(t)}</span>`)
        .join(" ");

      card.innerHTML = `
        <div>
          <div class="flex items-start justify-between mb-3">
            <div>
              <h3 class="text-base font-bold text-zinc-100">${escapeHtml(char.name)}</h3>
              <p class="text-xs text-zinc-500 font-mono">${char.gender} • ${char.age_group}</p>
            </div>
            <span class="text-xs font-mono px-2 py-0.5 rounded border ${roleColor}">${char.role.toUpperCase()}</span>
          </div>

          <div class="flex flex-wrap gap-1.5 mb-4">
            ${traitsHtml}
          </div>
        </div>

        <div class="pt-4 border-t border-zinc-800/80">
          <label class="block text-xs font-mono text-zinc-400 mb-1.5">Assigned Kokoro Voice</label>
          <div class="flex items-center space-x-2">
            <select class="voice-select flex-1 bg-zinc-900 border border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-amber-500" data-char-id="${charId}">
              ${voiceOptions}
            </select>
            <button class="btn-preview-voice px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-amber-400 rounded-md text-xs font-mono border border-zinc-700 transition" title="Preview Voice" data-char-id="${charId}">
              ▶
            </button>
          </div>
        </div>
      `;

      castGrid.appendChild(card);
    });

    // Wire up Voice Preview buttons
    document.querySelectorAll(".btn-preview-voice").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const charId = btn.getAttribute("data-char-id");
        const select = document.querySelector(`.voice-select[data-char-id="${charId}"]`);
        const voiceId = select ? select.value : "bm_george";

        const originalText = btn.textContent;
        btn.textContent = "⏳";
        btn.disabled = true;

        try {
          await audioEngine.playVoicePreview(`/api/voice-sample/${voiceId}`);
        } catch (err) {
          console.error("Preview failed:", err);
        } finally {
          btn.textContent = originalText;
          btn.disabled = false;
        }
      });
    });
  }

  // Save Cast Sheet
  btnSaveCast.addEventListener("click", async () => {
    if (!state.currentBook || !state.castSheet) return;

    btnSaveCast.textContent = "Saving...";
    btnSaveCast.disabled = true;

    try {
      // Collect updated voice assignments
      document.querySelectorAll(".voice-select").forEach((select) => {
        const charId = select.getAttribute("data-char-id");
        if (state.castSheet.characters[charId]) {
          state.castSheet.characters[charId].voice_id = select.value;
        }
      });

      const resp = await fetch(`/api/books/${state.currentBook}/cast`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(state.castSheet),
      });

      const res = await resp.json();
      btnSaveCast.textContent = "✓ Saved";
      setTimeout(() => {
        btnSaveCast.textContent = "Save Cast Sheet";
        btnSaveCast.disabled = false;
      }, 1800);
    } catch (err) {
      console.error("Failed to save cast sheet:", err);
      btnSaveCast.textContent = "Save Failed";
      btnSaveCast.disabled = false;
    }
  });

  // --------------------------------------------------------------------------
  // Outputs & Mastered Tracks
  // --------------------------------------------------------------------------
  async function loadOutputs() {
    try {
      const resp = await fetch("/api/outputs");
      const data = await resp.json();
      const files = data.outputs || [];

      outputsTableBody.innerHTML = "";
      if (files.length === 0) {
        outputsTableBody.innerHTML = `
          <tr>
            <td colspan="5" class="p-8 text-center text-zinc-500 font-mono text-sm">
              No produced audio tracks found in outputs/ yet. Produce a chapter to see files here.
            </td>
          </tr>
        `;
        return;
      }

      files.forEach((f) => {
        const tr = document.createElement("tr");
        tr.className = "border-b border-zinc-800/60 hover:bg-zinc-900/40 transition";

        const sizeKb = (f.size_bytes / 1024).toFixed(1);
        const durFormatted = f.duration_sec > 0 ? `${f.duration_sec}s` : "--";

        tr.innerHTML = `
          <td class="p-3 text-zinc-200 font-medium font-sans text-sm">${escapeHtml(f.name)}</td>
          <td class="p-3 font-mono text-xs uppercase text-zinc-400">${f.format}</td>
          <td class="p-3 font-mono text-xs text-zinc-400">${sizeKb} KB</td>
          <td class="p-3 font-mono text-xs text-amber-400">${durFormatted}</td>
          <td class="p-3 text-right space-x-2">
            ${
              f.format === "wav" || f.format === "mp3"
                ? `<audio controls preload="none" src="/api/outputs/file/${f.relative_path}" class="inline-block h-7 align-middle"></audio>`
                : ""
            }
            <a href="/api/outputs/file/${f.relative_path}" download="${f.name}" class="inline-block px-2.5 py-1 text-xs font-mono bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded border border-zinc-700 transition">
              Download
            </a>
          </td>
        `;
        outputsTableBody.appendChild(tr);
      });
    } catch (err) {
      console.error("Failed to load outputs:", err);
    }
  }

  // --------------------------------------------------------------------------
  // Utility
  // --------------------------------------------------------------------------
  function escapeHtml(text) {
    if (!text) return "";
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Initialize
  loadVoices();
  loadBooks();
});
