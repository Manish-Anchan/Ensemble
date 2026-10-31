import { useRef } from 'react';
import type { AudioFrequencyData } from '../lib/audioEngine';
import { SiriSheet } from '@/registry/orbe/siri-sheet/siri-sheet';
import type { OrbState } from '@/registry/lib/orb-state';
import { OrbStatus } from '@/registry/lib/orb-status';

interface VoiceOrbProps {
  speakerName?: string;
  role?: string;
  isPlaying?: boolean;
  freq?: AudioFrequencyData;
  state?: OrbState;
}

export function VoiceOrb({
  speakerName = 'Narrator',
  role = 'Protagonist',
  isPlaying = false,
  freq = { energy: 0, bass: 0, mid: 0, treble: 0 },
  state,
}: VoiceOrbProps) {
  const levelRef = useRef<number>(-1);
  levelRef.current = isPlaying ? Math.max(0.05, freq.energy) : -1;

  const orbState: OrbState = state || (isPlaying ? 'speaking' : 'idle');

  return (
    <div className="relative flex flex-col items-center justify-center p-6 rounded-2xl border border-white/[0.07] bg-[#000000] overflow-hidden select-none shadow-[0_8px_32px_rgba(0,0,0,0.8)]">
      {/* Siri Sheet Animated AI-Assistant Orb */}
      <div className="relative flex items-center justify-center my-3">
        <SiriSheet
          state={orbState}
          size={168}
          speed={1}
          colorFrom="#82f4ff"
          colorTo="#8e6cff"
          levelRef={levelRef}
        />
      </div>

      {/* Speaker Spotlight Label */}
      <div className="relative z-20 flex flex-col items-center space-y-1.5 mt-2 text-center">
        <div className="flex items-center space-x-2">
          <span className="text-xl font-bold tracking-tight text-[#F7F8F8]">
            {speakerName}
          </span>
          <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded border border-purple-500/30 bg-purple-500/10 text-purple-300 font-medium">
            {role}
          </span>
        </div>

        {/* Live Audio Reaction Badge */}
        <div className="flex items-center space-x-2 text-[11px] font-mono text-zinc-400">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              isPlaying ? 'bg-purple-400 animate-pulse' : 'bg-zinc-600'
            }`}
          />
          <OrbStatus state={orbState} />
          {isPlaying && (
            <>
              <span className="text-zinc-600">·</span>
              <span className="text-amber-400 font-medium">24kHz PCM</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
