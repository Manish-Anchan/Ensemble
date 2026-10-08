import React, { useRef, useEffect } from 'react';
import { getSpeakerStyle } from '../lib/colors';
import type { LineMetadata } from '../lib/audioEngine';
import { BookOpen } from 'lucide-react';

interface ScreenplayReaderProps {
  lines: LineMetadata[];
  activeLineIndex: number;
}

export const ScreenplayReader: React.FC<ScreenplayReaderProps> = ({
  lines,
  activeLineIndex,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const activeLineRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to center on active line
  useEffect(() => {
    if (activeLineRef.current) {
      activeLineRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [activeLineIndex]);

  if (lines.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-center text-zinc-500 space-y-3">
        <div className="w-14 h-14 rounded-2xl bg-zinc-900/60 border border-white/[0.06] flex items-center justify-center text-zinc-400">
          <BookOpen className="w-6 h-6" />
        </div>
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-zinc-300">The Stage is Quiet</h3>
          <p className="text-xs text-zinc-500 font-mono max-w-sm">
            Press Play on the dock below to direct the screenplay and stream live multi-cast voices.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-6 py-4 space-y-5 max-w-3xl mx-auto w-full pb-36"
    >
      {lines.map((line, idx) => {
        const lineNum = line.line_index || idx + 1;
        const isActive = lineNum === activeLineIndex;
        const isPassed = lineNum < activeLineIndex;
        const style = getSpeakerStyle(line.character_name || line.speaker);
        const initial = (line.character_name || line.speaker || 'C').charAt(0).toUpperCase();

        return (
          <div
            key={lineNum}
            ref={isActive ? activeLineRef : null}
            className={`transition-all duration-300 rounded-2xl p-5 border relative ${
              isActive
                ? 'bg-white/[0.04] border-white/[0.15] shadow-2xl scale-[1.01]'
                : isPassed
                ? 'bg-transparent border-transparent opacity-35 hover:opacity-70'
                : 'bg-transparent border-transparent opacity-75 hover:opacity-95'
            }`}
          >
            {/* Active Left Indicator Bar */}
            {isActive && (
              <div
                className="absolute left-0 top-4 bottom-4 w-1 rounded-r-full shadow-lg"
                style={{ backgroundColor: style.glow, boxShadow: `0 0 12px ${style.glow}` }}
              />
            )}

            <div className="flex items-start space-x-4">
              {/* Speaker Monogram Badge */}
              <div
                className={`w-9 h-9 rounded-full border ${style.avatar} flex items-center justify-center text-xs font-mono font-bold flex-shrink-0 mt-0.5 shadow-sm transition-transform ${
                  isActive ? 'scale-110 shadow-lg' : ''
                }`}
                style={{
                  boxShadow: isActive ? `0 0 16px ${style.glow}` : undefined,
                }}
              >
                {initial}
              </div>

              {/* Dialogue Content */}
              <div className="min-w-0 flex-1 space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2.5">
                    <span className={`font-bold text-sm ${style.text} tracking-tight`}>
                      {line.character_name || line.speaker}
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/[0.05] text-zinc-400 border border-white/[0.06]">
                      [{line.emotion || 'natural'}]
                    </span>
                  </div>
                  <span className="text-[10px] font-mono text-zinc-600">
                    #{lineNum}
                  </span>
                </div>

                <p
                  className={`text-base leading-relaxed font-sans transition-colors ${
                    isActive
                      ? 'text-white font-medium text-shadow-sm'
                      : 'text-zinc-300'
                  }`}
                >
                  {line.text}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
