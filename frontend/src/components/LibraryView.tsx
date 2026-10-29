import React, { useEffect, useState, useRef } from 'react';
import {
  Disc3,
  Download,
  Play,
  RefreshCw,
  FileText,
  UploadCloud,
  BookOpen,
  CheckCircle2,
  AlertCircle,
  Users,
  Sparkles,
  ArrowRight,
  HardDrive
} from 'lucide-react';

export interface BookMetadata {
  filename: string;
  title: string;
  author?: string;
  format: string;
  size_bytes?: number;
  has_cast_sheet?: boolean;
  cast_sheet_path?: string | null;
  total_chapters?: number | null;
  total_words?: number | null;
}

interface OutputTrack {
  filename: string;
  format: string;
  size_bytes: number;
  size_human: string;
  duration_human?: string;
  mtime: number;
  url: string;
}

interface LibraryViewProps {
  books: BookMetadata[];
  currentBook: string | null;
  onSelectBook: (filename: string) => void;
  onOpenCasting: (filename: string) => void;
  onRefreshBooks: () => Promise<void>;
}

export const LibraryView: React.FC<LibraryViewProps> = ({
  books,
  currentBook,
  onSelectBook,
  onOpenCasting,
  onRefreshBooks,
}) => {
  // Upload State
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<{
    filename: string;
    title: string;
    chapters: number;
    words: number;
  } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Mastered Outputs State
  const [tracks, setTracks] = useState<OutputTrack[]>([]);
  const [isLoadingTracks, setIsLoadingTracks] = useState(false);

  const fetchTracks = async () => {
    setIsLoadingTracks(true);
    try {
      const resp = await fetch('/api/outputs');
      const data = await resp.json();
      setTracks(data.outputs || []);
    } catch (err) {
      console.error('Failed to load output tracks:', err);
    } finally {
      setIsLoadingTracks(false);
    }
  };

  useEffect(() => {
    fetchTracks();
  }, []);

  const handleFileUpload = async (file: File) => {
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!['.pdf', '.epub'].includes(ext)) {
      setUploadError('Please select a valid .pdf or .epub fiction book.');
      return;
    }

    setIsUploading(true);
    setUploadError(null);
    setUploadSuccess(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const resp = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || `Upload failed with HTTP ${resp.status}`);
      }

      const data = await resp.json();
      setUploadSuccess({
        filename: data.filename,
        title: data.title || file.name.replace(/\.[^/.]+$/, '').replace(/_/g, ' '),
        chapters: data.total_chapters || 0,
        words: data.total_words || 0,
      });

      // Refresh parent books list so it appears in navigation
      await onRefreshBooks();
    } catch (err: any) {
      console.error('Upload error:', err);
      setUploadError(err.message || 'Failed to upload and ingest book.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return '--';
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="max-w-5xl mx-auto space-y-10 pb-32">
      {/* ========================================================================= */}
      {/* SECTION 1: INGESTION & UPLOAD DROPZONE */}
      {/* ========================================================================= */}
      <section className="space-y-3">
        <div className="flex items-center justify-between pb-2 border-b border-white/[0.08]">
          <div>
            <h2 className="text-lg font-bold tracking-tight text-white flex items-center space-x-2">
              <UploadCloud className="w-5 h-5 text-amber-400" />
              <span>Book Ingestion & Parser</span>
            </h2>
            <p className="text-xs text-zinc-400 font-mono mt-0.5">
              Upload raw PDF or EPUB fiction books. The engine extracts chapters, cleans typography, and builds 1,000-word dramatic scenes.
            </p>
          </div>
        </div>

        {/* Drag & Drop Card */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`relative cursor-pointer transition-all duration-300 rounded-2xl border-2 border-dashed p-8 text-center flex flex-col items-center justify-center space-y-3 ${
            isDragging
              ? 'border-amber-400/80 bg-amber-500/[0.06] scale-[1.005]'
              : 'border-white/[0.12] bg-[#0c0c10]/70 hover:border-white/[0.24] hover:bg-[#121218]/90'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.epub"
            className="hidden"
            onChange={(e) => {
              if (e.target.files && e.target.files[0]) {
                handleFileUpload(e.target.files[0]);
              }
            }}
          />

          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-amber-500/20 to-amber-300/10 border border-amber-500/30 flex items-center justify-center text-amber-400 shadow-[0_0_20px_rgba(251,191,36,0.15)]">
            {isUploading ? (
              <RefreshCw className="w-6 h-6 animate-spin text-amber-400" />
            ) : (
              <UploadCloud className="w-6 h-6" />
            )}
          </div>

          <div className="space-y-1">
            <p className="text-sm font-semibold text-zinc-100">
              {isUploading
                ? 'Ingesting & Slicing into Dramatic Scenes...'
                : 'Drop your EPUB or PDF book here, or click to browse'}
            </p>
            <p className="text-xs text-zinc-500 font-mono">
              Supports standard fiction .EPUB and .PDF files • Auto-detects Table of Contents & Chapter Breaks
            </p>
          </div>

          {/* Quick Format Badges */}
          <div className="flex items-center space-x-2 pt-1 font-mono text-[10px]">
            <span className="px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-semibold">
              EPUB 3.0
            </span>
            <span className="px-2 py-0.5 rounded-full bg-violet-500/10 text-violet-400 border border-violet-500/20 font-semibold">
              PDF (Vector)
            </span>
            <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold">
              Spatial Margin Clipping
            </span>
          </div>
        </div>

        {/* Upload Success Banner */}
        {uploadSuccess && (
          <div className="p-4 rounded-xl bg-emerald-500/[0.08] border border-emerald-500/30 flex items-center justify-between animate-in fade-in slide-in-from-top-1 text-xs">
            <div className="flex items-center space-x-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
              <div>
                <p className="font-semibold text-emerald-300 font-sans text-sm">
                  Successfully Ingested: {uploadSuccess.title}
                </p>
                <p className="text-zinc-400 font-mono text-[11px] mt-0.5">
                  {uploadSuccess.filename} • {uploadSuccess.chapters} Chapters • {uploadSuccess.words.toLocaleString()} Words parsed into 1,000w scene chunks
                </p>
              </div>
            </div>

            <button
              onClick={() => onSelectBook(uploadSuccess.filename)}
              className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-semibold font-sans text-xs flex items-center space-x-1.5 transition shadow-[0_0_15px_rgba(16,185,129,0.3)] hover:scale-[1.02]"
            >
              <span>Listen in Studio</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Upload Error Banner */}
        {uploadError && (
          <div className="p-3.5 rounded-xl bg-red-500/[0.08] border border-red-500/30 flex items-center space-x-3 text-xs text-red-300">
            <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
            <span>{uploadError}</span>
          </div>
        )}
      </section>

      {/* ========================================================================= */}
      {/* SECTION 2: BOOKSHELF / INGESTED WORKS */}
      {/* ========================================================================= */}
      <section className="space-y-4">
        <div className="flex items-center justify-between pb-2 border-b border-white/[0.08]">
          <div>
            <h2 className="text-lg font-bold tracking-tight text-white flex items-center space-x-2">
              <BookOpen className="w-5 h-5 text-emerald-400" />
              <span>Your Bookshelf</span>
              <span className="text-xs font-mono text-zinc-500 font-normal">
                ({books.length} ready to direct)
              </span>
            </h2>
            <p className="text-xs text-zinc-400 font-mono mt-0.5">
              Select any novel to direct into a line-by-line screenplay and stream audio via Kokoro ONNX GPU.
            </p>
          </div>

          <button
            onClick={onRefreshBooks}
            className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-lg text-xs font-mono border border-white/[0.08] transition flex items-center space-x-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5 text-zinc-400" />
            <span>Refresh</span>
          </button>
        </div>

        {books.length === 0 ? (
          <div className="p-12 text-center flex flex-col items-center justify-center space-y-3 bg-[#0c0c10]/50 rounded-2xl border border-white/[0.06]">
            <BookOpen className="w-10 h-10 text-zinc-600" />
            <p className="text-sm font-semibold text-zinc-300">No Books Found</p>
            <p className="text-xs text-zinc-500 font-mono max-w-sm">
              Drag and drop an EPUB or PDF above to start generating multi-character audio dramas.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {books.map((b) => {
              const isSelected = currentBook === b.filename;
              const isEpub = b.format.toLowerCase() === 'epub';

              return (
                <div
                  key={b.filename}
                  className={`group relative rounded-2xl p-5 border transition-all duration-200 flex flex-col justify-between space-y-4 ${
                    isSelected
                      ? 'bg-gradient-to-b from-[#14141e] to-[#0d0d14] border-emerald-500/40 shadow-[0_0_25px_rgba(16,185,129,0.08)]'
                      : 'bg-[#0c0c10]/80 hover:bg-[#12121a] border-white/[0.08] hover:border-white/[0.18]'
                  }`}
                >
                  {/* Top Row: Format & Status */}
                  <div className="flex items-start justify-between">
                    <div className="flex items-center space-x-2">
                      <span
                        className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded uppercase border ${
                          isEpub
                            ? 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
                            : 'bg-violet-500/10 text-violet-300 border-violet-500/30'
                        }`}
                      >
                        {b.format}
                      </span>

                      {isSelected && (
                        <span className="flex items-center space-x-1 text-[11px] font-mono font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                          <span>Active in Studio</span>
                        </span>
                      )}
                    </div>

                    {b.has_cast_sheet ? (
                      <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded flex items-center space-x-1">
                        <Users className="w-3 h-3" />
                        <span>Cast Ready</span>
                      </span>
                    ) : (
                      <span className="text-[10px] font-mono text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded flex items-center space-x-1">
                        <Sparkles className="w-3 h-3" />
                        <span>Auto-Cast on Stream</span>
                      </span>
                    )}
                  </div>

                  {/* Book Info */}
                  <div className="space-y-1">
                    <h3 className="text-base font-bold text-white group-hover:text-amber-200 transition-colors">
                      {b.title}
                    </h3>
                    <p className="text-xs text-zinc-400 font-mono">
                      {b.author || 'Classic Literature'} • {b.filename}
                    </p>
                  </div>

                  {/* Metadata Chips */}
                  <div className="flex items-center space-x-3 text-[11px] font-mono text-zinc-400 pt-1 border-t border-white/[0.04]">
                    {b.total_chapters !== undefined && b.total_chapters !== null && (
                      <span className="flex items-center space-x-1">
                        <BookOpen className="w-3 h-3 text-zinc-500" />
                        <span>{b.total_chapters} Chapters</span>
                      </span>
                    )}
                    {b.total_words !== undefined && b.total_words !== null && (
                      <span className="flex items-center space-x-1">
                        <span>{b.total_words.toLocaleString()} words</span>
                      </span>
                    )}
                    <span className="flex items-center space-x-1 text-zinc-500">
                      <HardDrive className="w-3 h-3" />
                      <span>{formatFileSize(b.size_bytes)}</span>
                    </span>
                  </div>

                  {/* Action Buttons */}
                  <div className="grid grid-cols-2 gap-2 pt-2">
                    <button
                      onClick={() => onSelectBook(b.filename)}
                      className={`py-2 px-3 rounded-xl font-medium text-xs flex items-center justify-center space-x-1.5 transition ${
                        isSelected
                          ? 'bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold shadow-[0_0_15px_rgba(16,185,129,0.25)]'
                          : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-100 hover:text-white border border-white/[0.08]'
                      }`}
                    >
                      <Play className="w-3.5 h-3.5 fill-current" />
                      <span>{isSelected ? 'Resume in Studio' : 'Listen in Studio'}</span>
                    </button>

                    <button
                      onClick={() => onOpenCasting(b.filename)}
                      className="py-2 px-3 rounded-xl bg-zinc-900/80 hover:bg-zinc-800 text-zinc-300 hover:text-white font-medium text-xs border border-white/[0.08] flex items-center justify-center space-x-1.5 transition"
                    >
                      <Users className="w-3.5 h-3.5 text-amber-400" />
                      <span>Casting Room</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* ========================================================================= */}
      {/* SECTION 3: MASTERED OUTPUT AUDIO TRACKS */}
      {/* ========================================================================= */}
      <section className="space-y-4">
        <div className="flex items-center justify-between pb-2 border-b border-white/[0.08]">
          <div>
            <h2 className="text-lg font-bold tracking-tight text-white flex items-center space-x-2">
              <Disc3 className="w-5 h-5 text-zinc-400" />
              <span>Mastered Audio Productions</span>
              <span className="text-xs font-mono text-zinc-500 font-normal">
                ({tracks.length} tracks in outputs/)
              </span>
            </h2>
            <p className="text-xs text-zinc-400 font-mono mt-0.5">
              Batch-rendered full chapters and multi-speaker masters stored on disk.
            </p>
          </div>

          <button
            onClick={fetchTracks}
            disabled={isLoadingTracks}
            className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-lg text-xs font-mono border border-white/[0.08] transition flex items-center space-x-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingTracks ? 'animate-spin text-amber-400' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>

        <div className="bezel-outer overflow-hidden">
          <div className="bezel-inner overflow-hidden">
            {tracks.length === 0 ? (
              <div className="p-8 text-center flex flex-col items-center justify-center space-y-2">
                <Disc3 className="w-8 h-8 text-zinc-600" />
                <p className="text-sm font-semibold text-zinc-300">No Mastered Tracks Yet</p>
                <p className="text-xs text-zinc-500 font-mono max-w-sm">
                  Run batch production via CLI or stream full chapters in Studio Stage to generate master audio files.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-white/[0.06] bg-zinc-950/40 text-[11px] font-mono text-zinc-400">
                      <th className="p-3.5">Track Name</th>
                      <th className="p-3.5">Format</th>
                      <th className="p-3.5">File Size</th>
                      <th className="p-3.5">Last Modified</th>
                      <th className="p-3.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04] text-xs font-mono">
                    {tracks.map((track) => (
                      <tr
                        key={track.filename}
                        className="hover:bg-white/[0.02] transition-colors group"
                      >
                        <td className="p-3.5 text-zinc-200 font-medium font-sans">
                          <div className="flex items-center space-x-2.5">
                            <div className="w-7 h-7 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                              {track.format === 'json' ? (
                                <FileText className="w-3.5 h-3.5" />
                              ) : (
                                <Disc3 className="w-3.5 h-3.5" />
                              )}
                            </div>
                            <span>{track.filename}</span>
                          </div>
                        </td>
                        <td className="p-3.5 text-zinc-400 uppercase">{track.format}</td>
                        <td className="p-3.5 text-zinc-300">{track.size_human}</td>
                        <td className="p-3.5 text-zinc-500">
                          {new Date(track.mtime * 1000).toLocaleDateString()}
                        </td>
                        <td className="p-3.5 text-right">
                          <a
                            href={track.url}
                            download={track.filename}
                            className="inline-flex items-center space-x-1.5 px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-lg text-xs transition border border-white/[0.06]"
                          >
                            <Download className="w-3 h-3 text-zinc-400" />
                            <span>Download</span>
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
};
