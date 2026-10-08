export interface SpeakerStyle {
  badge: string;
  text: string;
  border: string;
  bg: string;
  avatar: string;
  glow: string;
  orbGradient: string;
}

const characterPalettes: SpeakerStyle[] = [
  {
    badge: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
    text: 'text-sky-400',
    border: 'border-sky-500/30',
    bg: 'bg-sky-500/10',
    avatar: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
    glow: 'rgba(56, 189, 248, 0.35)',
    orbGradient: 'from-sky-400 via-cyan-500 to-blue-600',
  },
  {
    badge: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
    text: 'text-rose-400',
    border: 'border-rose-500/30',
    bg: 'bg-rose-500/10',
    avatar: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
    glow: 'rgba(251, 113, 133, 0.35)',
    orbGradient: 'from-rose-400 via-pink-500 to-red-600',
  },
  {
    badge: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    text: 'text-emerald-400',
    border: 'border-emerald-500/30',
    bg: 'bg-emerald-500/10',
    avatar: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    glow: 'rgba(52, 211, 153, 0.35)',
    orbGradient: 'from-emerald-400 via-teal-500 to-green-600',
  },
  {
    badge: 'bg-violet-500/10 text-violet-400 border-violet-500/30',
    text: 'text-violet-400',
    border: 'border-violet-500/30',
    bg: 'bg-violet-500/10',
    avatar: 'bg-violet-500/20 text-violet-300 border-violet-500/40',
    glow: 'rgba(167, 139, 250, 0.35)',
    orbGradient: 'from-violet-400 via-purple-500 to-indigo-600',
  },
  {
    badge: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    text: 'text-amber-400',
    border: 'border-amber-500/30',
    bg: 'bg-amber-500/10',
    avatar: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    glow: 'rgba(245, 158, 11, 0.35)',
    orbGradient: 'from-amber-400 via-yellow-500 to-orange-600',
  },
];

const speakerColorCache = new Map<string, SpeakerStyle>();
let paletteIndex = 0;

export function getSpeakerStyle(speakerName?: string): SpeakerStyle {
  if (!speakerName) return characterPalettes[0];
  const name = speakerName.trim().toLowerCase();

  if (name.includes('narrator')) {
    return {
      badge: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
      text: 'text-amber-400',
      border: 'border-amber-500/30',
      bg: 'bg-amber-500/10',
      avatar: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
      glow: 'rgba(245, 158, 11, 0.4)',
      orbGradient: 'from-amber-400 via-amber-500 to-yellow-600',
    };
  }

  if (!speakerColorCache.has(name)) {
    speakerColorCache.set(name, characterPalettes[paletteIndex % characterPalettes.length]);
    paletteIndex++;
  }

  return speakerColorCache.get(name)!;
}
