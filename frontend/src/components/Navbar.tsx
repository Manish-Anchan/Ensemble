import React from 'react';
import { Sparkles, Disc3, Users, PlayCircle, BookOpen } from 'lucide-react';

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

interface NavbarProps {
  activeTab: 'stage' | 'casting' | 'library';
  onTabChange: (tab: 'stage' | 'casting' | 'library') => void;
  books: Book[];
  currentBook: string | null;
  onBookChange: (book: string) => void;
  chapters: Chapter[];
  currentChapter: Chapter | null;
  onChapterChange: (chapterIndex: number) => void;
  streamingStatus: string;
  statusColor: 'amber' | 'green' | 'red' | 'zinc';
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onTabChange,
  books,
  currentBook,
  onBookChange,
  chapters,
  currentChapter,
  onChapterChange,
  streamingStatus,
  statusColor,
}) => {
  return (
    <header className="sticky top-0 z-40 px-6 py-3 border-b border-white/[0.06] bg-[#070709]/85 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        {/* Brand & Tabs */}
        <div className="flex items-center space-x-7">
          <div className="flex items-center space-x-2.5">
            <div className="w-2.5 h-2.5 rounded-full bg-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.8)] animate-pulse" />
            <div className="flex items-baseline space-x-1.5 font-mono">
              <span className="text-base font-extrabold tracking-tight text-white">ENSEMBLE</span>
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-zinc-800/80 text-zinc-400 border border-zinc-700/60">
                STUDIO
              </span>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center space-x-1 text-xs font-medium">
            <button
              onClick={() => onTabChange('stage')}
              className={`px-3.5 py-1.5 rounded-xl transition-all flex items-center space-x-2 ${
                activeTab === 'stage'
                  ? 'bg-white/[0.08] text-white border border-white/[0.12] font-semibold shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.04]'
              }`}
            >
              <PlayCircle className="w-3.5 h-3.5 text-amber-400" />
              <span>Studio Stage</span>
            </button>

            <button
              onClick={() => onTabChange('casting')}
              className={`px-3.5 py-1.5 rounded-xl transition-all flex items-center space-x-2 ${
                activeTab === 'casting'
                  ? 'bg-white/[0.08] text-white border border-white/[0.12] font-semibold shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.04]'
              }`}
            >
              <Users className="w-3.5 h-3.5 text-sky-400" />
              <span>Casting Room</span>
            </button>

            <button
              onClick={() => onTabChange('library')}
              className={`px-3.5 py-1.5 rounded-xl transition-all flex items-center space-x-2 ${
                activeTab === 'library'
                  ? 'bg-white/[0.08] text-white border border-white/[0.12] font-semibold shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.04]'
              }`}
            >
              <Disc3 className="w-3.5 h-3.5 text-emerald-400" />
              <span>Library</span>
            </button>
          </nav>
        </div>

        {/* Dropdowns & Telemetry */}
        <div className="flex items-center space-x-3">
          {/* Hardware Chip */}
          <div className="hidden lg:flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-zinc-900/90 border border-white/[0.07] text-[11px] font-mono text-zinc-400">
            <Sparkles className="w-3 h-3 text-amber-400" />
            <span className="text-zinc-300 font-medium">RTX 2050 CUDA</span>
          </div>

          {/* Book Dropdown */}
          <div className="flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-zinc-900/90 border border-white/[0.07] text-xs font-mono">
            <BookOpen className="w-3 h-3 text-zinc-400" />
            <select
              value={currentBook || ''}
              onChange={(e) => onBookChange(e.target.value)}
              className="bg-transparent text-zinc-200 focus:outline-none cursor-pointer pr-3 text-xs"
            >
              {books.map((b) => (
                <option key={b.filename} value={b.filename} className="bg-zinc-900 text-zinc-200">
                  {b.title}
                </option>
              ))}
            </select>
          </div>

          {/* Chapter Dropdown */}
          <div className="flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-zinc-900/90 border border-white/[0.07] text-xs font-mono">
            <select
              value={currentChapter?.index || 1}
              onChange={(e) => onChapterChange(parseInt(e.target.value, 10))}
              className="bg-transparent text-zinc-200 focus:outline-none cursor-pointer pr-2 text-xs"
            >
              {chapters.map((ch) => (
                <option key={ch.index} value={ch.index} className="bg-zinc-900 text-zinc-200">
                  Chapter {ch.index}: {ch.title}
                </option>
              ))}
            </select>
            {currentChapter && (
              <span className="text-zinc-500 text-[10px] pl-1 font-mono">
                {currentChapter.scene_count} scenes
              </span>
            )}
          </div>

          {/* Live Status Pill */}
          <div
            className={`text-xs font-mono px-3 py-1 rounded-full flex items-center space-x-1.5 transition-all ${
              statusColor === 'amber'
                ? 'bg-amber-950/80 text-amber-300 border border-amber-500/40 shadow-[0_0_12px_rgba(245,158,11,0.2)]'
                : statusColor === 'green'
                ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/40 shadow-[0_0_12px_rgba(52,211,153,0.2)]'
                : statusColor === 'red'
                ? 'bg-red-950/80 text-red-300 border border-red-500/40'
                : 'bg-zinc-900 text-zinc-400 border border-white/[0.08]'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                statusColor === 'amber'
                  ? 'bg-amber-400 animate-pulse'
                  : statusColor === 'green'
                  ? 'bg-emerald-400 animate-pulse'
                  : statusColor === 'red'
                  ? 'bg-red-400'
                  : 'bg-zinc-500'
              }`}
            />
            <span className="font-medium">{streamingStatus}</span>
          </div>
        </div>
      </div>
    </header>
  );
};
