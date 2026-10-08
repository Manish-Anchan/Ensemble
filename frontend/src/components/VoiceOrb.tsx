import React from 'react';
import { getSpeakerStyle } from '../lib/colors';

interface VoiceOrbProps {
  speakerName: string;
  voiceId: string;
  emotion: string;
  energy: number; // 0.0 to 1.0 from real-time audio
  isPlaying: boolean;
}

export const VoiceOrb: React.FC<VoiceOrbProps> = ({
  speakerName,
  voiceId,
  emotion,
  energy,
  isPlaying,
}) => {
  const style = getSpeakerStyle(speakerName);
  const initial = speakerName ? speakerName.charAt(0).toUpperCase() : 'N';

  // Dynamic scale and ripple driven by live audio energy
  const scale = isPlaying ? 1 + energy * 0.45 : 1.0;
  const outerRippleScale = isPlaying ? 1.2 + energy * 0.9 : 1.1;
  const glowOpacity = isPlaying ? 0.35 + energy * 0.55 : 0.2;

  return (
    <div className="flex flex-col items-center justify-center py-6 select-none relative">
      {/* Background radial ambient glow */}
      <div
        className="absolute w-80 h-80 rounded-full pointer-events-none transition-all duration-300"
        style={{
          background: `radial-gradient(circle, ${style.glow} 0%, transparent 70%)`,
          opacity: glowOpacity,
          transform: `scale(${scale})`,
        }}
      />

      {/* The Concentric Living Voice Orb */}
      <div className="relative flex items-center justify-center w-40 h-40">
        {/* Outer Ripple Ring */}
        <div
          className="absolute inset-0 rounded-full border border-white/10 transition-transform duration-100 ease-out"
          style={{
            transform: `scale(${outerRippleScale})`,
            borderColor: isPlaying ? style.glow : 'rgba(255,255,255,0.06)',
          }}
        />

        {/* Secondary Harmonic Ring */}
        <div
          className="absolute inset-2 rounded-full border border-white/15 transition-transform duration-150 ease-out"
          style={{
            transform: `scale(${1 + energy * 0.3})`,
            borderColor: isPlaying ? style.glow : 'rgba(255,255,255,0.08)',
          }}
        />

        {/* Main Fluid Core Sphere */}
        <div
          className={`w-28 h-28 rounded-full bg-gradient-to-tr ${style.orbGradient} p-1 shadow-2xl transition-transform duration-100 ease-out flex items-center justify-center`}
          style={{
            transform: `scale(${scale})`,
            boxShadow: `0 0 35px ${style.glow}`,
          }}
        >
          {/* Inner glass core with initial */}
          <div className="w-full h-full rounded-full bg-black/60 backdrop-blur-md flex items-center justify-center border border-white/20">
            <span className="text-2xl font-mono font-black text-white tracking-wider">
              {initial}
            </span>
          </div>
        </div>
      </div>

      {/* Speaker Name & Dynamic Emotion Pill */}
      <div className="mt-4 text-center space-y-1 relative z-10">
        <div className="flex items-center justify-center space-x-2">
          <span className={`text-base font-extrabold tracking-tight ${style.text}`}>
            {speakerName || 'Narrator'}
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/[0.06] text-zinc-300 border border-white/[0.08]">
            [{emotion || 'natural'}]
          </span>
        </div>

        <div className="flex items-center justify-center space-x-2 text-[11px] font-mono text-zinc-500">
          <span>Voice: <strong className="text-zinc-300 font-medium">{voiceId || 'bm_george'}</strong></span>
          <span>•</span>
          <span>24kHz Stereo</span>
        </div>
      </div>
    </div>
  );
};
