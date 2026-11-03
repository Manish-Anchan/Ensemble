import { useMemo } from 'react';
import type { OrbState } from '@/registry/lib/orb-state';
import { SiriSheet } from '@/registry/orbe/siri-sheet/siri-sheet';

export interface SiriPillProps {
  state?: OrbState;
  label?: string;
  size?: number;
  className?: string;
  onClick?: () => void;
}

export function SiriPill({
  state = 'connecting',
  label = 'Connecting',
  size = 34,
  className = '',
  onClick,
}: SiriPillProps) {
  const colors = useMemo(() => {
    switch (state) {
      case 'thinking':
        return { from: '#ffd180', to: '#c084fc' }; // warm amber & violet neural flare
      case 'connecting':
        return { from: '#7fe6e3', to: '#818cf8' }; // cyan & indigo luminous wave
      case 'speaking':
        return { from: '#82f4ff', to: '#8e6cff' }; // vibrant Siri cyan & purple
      case 'error':
        return { from: '#fb7185', to: '#f43f5e' }; // rose / coral warning
      default:
        return { from: '#82f4ff', to: '#8e6cff' };
    }
  }, [state]);

  const speed = state === 'thinking' ? 1.2 : state === 'connecting' ? 0.8 : 1;

  return (
    <div className={`stage-pill-wrapper ${className}`} onClick={onClick}>
      <div className="siri-pill" role="status" aria-live="polite">
        <div className="siri-pill-orb">
          <SiriSheet
            state={state}
            size={size}
            speed={speed}
            colorFrom={colors.from}
            colorTo={colors.to}
          />
        </div>
        <div className="siri-pill-content">
          <span className="siri-pill-label">{label}</span>
        </div>
      </div>
    </div>
  );
}
