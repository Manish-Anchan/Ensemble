import React from 'react';
import { Play, Pause, Square, Volume2, Layers } from 'lucide-react';
import { getSpeakerStyle } from '../lib/colors';

interface BottomPlayerDockProps {
  isStreaming: boolean;
  isPaused: boolean;
  isPlaying: boolean;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  activeSpeakerName: string;
  activeVoiceId: string;
  currentLine: number;
  totalLines: number;
  bufferedSec: number;
  bufferedCount: number;
  scope: number;
  onScopeChange: (scope: number) => void;
  volume: number;
  onVolumeChange: (vol: number) => void;
}

export const BottomPlayerDock: React.FC<BottomPlayerDockProps> = ({
  isStreaming,
  isPaused,
  isPlaying,
  onStart,
  onPause,
  onResume,
  onStop,
  activeSpeakerName,
  activeVoiceId,
  currentLine,
  totalLines,
  bufferedSec,
  bufferedCount,
  scope,
  onScopeChange,
  volume,
  onVolumeChange,
}) => {
  const style = getSpeakerStyle(activeSpeakerName);
  const progressPct = totalLines > 0 ? (currentLine / totalLines) * 100 : 0;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 w-[92%] max-w-4xl">
      <div className="bezel-outer bg-[#0d0d12]/90 backdrop-blur-2xl border border-white/[0.1] shadow-2xl p-2.5 rounded-2xl">
        <div className="bezel-inner bg-[#121218]/95 px-5 py-3 rounded-xl flex items-center justify-between gap-6">
          {/* Left: Active Voice Monogram Chip */}
          <div className="flex items-center space-x-3 min-w-[160px]">
            <div
              className={`w-9 h-9 rounded-full border ${style.avatar} flex items-center justify-center text-xs font-mono font-bold flex-shrink-0 shadow-sm`}
            >
              {(activeSpeakerName || 'N').charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className={`text-xs font-bold truncate ${style.text}`}>
                {activeSpeakerName || 'Narrator'}
              </p>
              <p className="text-[10px] font-mono text-zinc-500 truncate">
                {activeVoiceId || 'bm_george'}
              </p>
            </div>
          </div>

          {/* Center: Transport Controls & Scrubber */}
          <div className="flex-1 flex flex-col items-center space-y-1.5 max-w-md">
            <div className="flex items-center space-x-3">
              {!isStreaming && !isPlaying && !isPaused ? (
                <button
                  onClick={onStart}
                  className="w-10 h-10 rounded-full bg-amber-500 hover:bg-amber-400 active:scale-95 text-zinc-950 font-bold flex items-center justify-center transition-all shadow-[0_0_20px_rgba(245,158,11,0.35)]"
                  title="Synthesize & Stream"
                >
                  <Play className="w-4 h-4 fill-current ml-0.5 text-zinc-950" />
                </button>
              ) : (
                <>
                  <button
                    onClick={isPaused ? onResume : onPause}
                    className="w-10 h-10 rounded-full bg-white text-zinc-950 hover:bg-zinc-200 active:scale-95 flex items-center justify-center transition-all shadow-md"
                    title={isPaused ? 'Resume Playback' : 'Pause Playback'}
                  >
                    {isPaused ? (
                      <Play className="w-4 h-4 fill-current ml-0.5 text-zinc-950" />
                    ) : (
                      <Pause className="w-4 h-4 fill-current text-zinc-950" />
                    )}
                  </button>

                  <button
                    onClick={onStop}
                    className="w-8 h-8 rounded-full bg-zinc-800 hover:bg-red-950/80 hover:text-red-300 text-zinc-400 border border-white/[0.06] flex items-center justify-center transition-all"
                    title="Stop Stream"
                  >
                    <Square className="w-3 h-3 fill-current" />
                  </button>
                </>
              )}
            </div>

            {/* Scrubber Line */}
            <div className="w-full flex items-center space-x-3 text-[10px] font-mono text-zinc-500">
              <span className="w-12 text-right">Line {currentLine}</span>
              <div className="flex-1 bg-zinc-800/80 h-1.5 rounded-full overflow-hidden border border-white/[0.04]">
                <div
                  className="bg-gradient-to-r from-amber-500 to-amber-300 h-full transition-all duration-300 shadow-[0_0_8px_rgba(245,158,11,0.5)]"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <span className="w-12">{totalLines} total</span>
            </div>
          </div>

          {/* Right: Scope, Buffer Badge, Volume */}
          <div className="flex items-center space-x-3 min-w-[200px] justify-end">
            {/* Scope Pill Toggle */}
            <button
              onClick={() => onScopeChange(scope === 0 ? 1 : 0)}
              disabled={isStreaming}
              className="px-2.5 py-1 rounded-lg bg-zinc-900 border border-white/[0.08] text-[10px] font-mono text-zinc-300 hover:text-white transition flex items-center space-x-1 disabled:opacity-50"
              title="Toggle Scope"
            >
              <Layers className="w-3 h-3 text-amber-400" />
              <span>{scope === 1 ? '1 Scene' : 'Full Ch'}</span>
            </button>

            {/* Buffer Health Badge */}
            <span
              className={`text-[10px] font-mono px-2 py-0.5 rounded-md border transition-all ${
                bufferedSec >= 4.0
                  ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/30'
                  : bufferedSec > 0
                  ? 'bg-amber-950/80 text-amber-300 border-amber-500/30'
                  : 'bg-zinc-900 text-zinc-500 border-white/[0.06]'
              }`}
              title="Jitter Buffer Status"
            >
              {bufferedSec.toFixed(1)}s ({bufferedCount})
            </span>

            {/* Volume Control */}
            <div className="flex items-center space-x-1.5 w-24">
              <Volume2 className="w-3.5 h-3.5 text-zinc-400 flex-shrink-0" />
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={volume}
                onChange={(e) => onVolumeChange(parseFloat(e.target.value))}
                className="w-full accent-amber-500 cursor-pointer h-4"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
