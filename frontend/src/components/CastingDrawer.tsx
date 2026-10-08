import React, { useState } from 'react';
import { Users, Save, Check, Volume2 } from 'lucide-react';
import { getSpeakerStyle } from '../lib/colors';
import { StudioAudioEngine } from '../lib/audioEngine';

interface Voice {
  voice_id: string;
  name: string;
  gender: string;
  accent: string;
  timbre: string;
}

interface CharacterProfile {
  name: string;
  role: string;
  gender: string;
  age_group: string;
  voice_id: string;
  personality_traits: string[];
}

interface CastSheet {
  book_title: string;
  narrator_id: string;
  characters: Record<string, CharacterProfile>;
}

interface CastingDrawerProps {
  castSheet: CastSheet | null;
  voices: Voice[];
  audioEngine: StudioAudioEngine;
  onSaveCast: (updatedSheet: CastSheet) => Promise<void>;
}

export const CastingDrawer: React.FC<CastingDrawerProps> = ({
  castSheet,
  voices,
  audioEngine,
  onSaveCast,
}) => {
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
  const [localCast, setLocalCast] = useState<CastSheet | null>(castSheet);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  React.useEffect(() => {
    setLocalCast(castSheet);
  }, [castSheet]);

  const handleVoiceChange = (charId: string, newVoiceId: string) => {
    if (!localCast) return;
    setLocalCast({
      ...localCast,
      characters: {
        ...localCast.characters,
        [charId]: {
          ...localCast.characters[charId],
          voice_id: newVoiceId,
        },
      },
    });
  };

  const handleAudition = async (voiceId: string) => {
    setPlayingVoiceId(voiceId);
    try {
      await audioEngine.playVoicePreview(`/api/voice-sample/${voiceId}`);
    } catch (err) {
      console.error('Failed to audition voice:', err);
    } finally {
      setPlayingVoiceId(null);
    }
  };

  const handleSave = async () => {
    if (!localCast) return;
    setIsSaving(true);
    try {
      await onSaveCast(localCast);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } catch (err) {
      console.error('Failed to save cast:', err);
    } finally {
      setIsSaving(false);
    }
  };

  if (!localCast || Object.keys(localCast.characters || {}).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-16 text-center text-zinc-500 space-y-3 max-w-md mx-auto">
        <div className="w-12 h-12 rounded-2xl bg-zinc-900 border border-white/[0.06] flex items-center justify-center text-zinc-400">
          <Users className="w-6 h-6" />
        </div>
        <p className="text-sm font-semibold text-zinc-300">No Cast Sheet Available</p>
        <p className="text-xs text-zinc-500 font-mono">
          Run live stream to auto-cast characters or generate from the CLI casting producer.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-white flex items-center space-x-2">
            <span>Character Casting Room</span>
            <span className="text-xs font-mono text-zinc-500 font-normal">
              ({Object.keys(localCast.characters).length} roles)
            </span>
          </h2>
          <p className="text-xs text-zinc-400 font-mono mt-0.5">
            Assign and audition distinct Kokoro neural voices for each character profile.
          </p>
        </div>

        <button
          onClick={handleSave}
          disabled={isSaving}
          className="px-4 py-2 bg-amber-500 hover:bg-amber-400 active:scale-[0.98] text-zinc-950 font-bold rounded-xl text-xs font-mono transition shadow-lg shadow-amber-500/15 flex items-center space-x-1.5 disabled:opacity-50"
        >
          {saveSuccess ? (
            <>
              <Check className="w-3.5 h-3.5 text-zinc-950" />
              <span>Saved!</span>
            </>
          ) : (
            <>
              <Save className="w-3.5 h-3.5 text-zinc-950" />
              <span>{isSaving ? 'Saving...' : 'Save Cast Sheet'}</span>
            </>
          )}
        </button>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {Object.entries(localCast.characters).map(([charId, char]) => {
          const style = getSpeakerStyle(char.name);
          const initial = (char.name || 'C').charAt(0).toUpperCase();
          const isAuditioning = playingVoiceId === char.voice_id;

          return (
            <div key={charId} className="bezel-outer flex flex-col justify-between">
              <div className="bezel-inner p-5 flex flex-col justify-between h-full space-y-4">
                {/* Character Profile Header */}
                <div>
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center space-x-3">
                      <div
                        className={`w-10 h-10 rounded-full border-2 ${style.avatar} flex items-center justify-center text-sm font-mono font-bold flex-shrink-0 shadow-sm`}
                      >
                        {initial}
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-white tracking-tight">
                          {char.name}
                        </h3>
                        <p className="text-[11px] text-zinc-400 font-mono">
                          {char.gender} • {char.age_group}
                        </p>
                      </div>
                    </div>

                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${style.badge}`}
                    >
                      {char.role.toUpperCase()}
                    </span>
                  </div>

                  {/* Traits Chips */}
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {(char.personality_traits || []).slice(0, 4).map((trait, i) => (
                      <span
                        key={i}
                        className="text-[10px] bg-white/[0.04] text-zinc-400 px-2 py-0.5 rounded border border-white/[0.06] font-mono"
                      >
                        {trait}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Voice Selector & Audition */}
                <div className="pt-3.5 border-t border-white/[0.06] space-y-2">
                  <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400">
                    <span>Voice Assignment</span>
                    <span className="text-[10px] text-zinc-500">24kHz Stereo</span>
                  </div>

                  <div className="flex items-center space-x-2">
                    <select
                      value={char.voice_id}
                      onChange={(e) => handleVoiceChange(charId, e.target.value)}
                      className="flex-1 bg-zinc-900 border border-white/[0.1] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-amber-500 font-mono cursor-pointer"
                    >
                      {voices.map((v) => (
                        <option key={v.voice_id} value={v.voice_id} className="bg-zinc-900">
                          {v.name} ({v.accent.toUpperCase()} {v.gender.toUpperCase()} • {v.timbre})
                        </option>
                      ))}
                    </select>

                    <button
                      onClick={() => handleAudition(char.voice_id)}
                      disabled={isAuditioning}
                      className="px-3 py-1.5 bg-zinc-800/90 hover:bg-zinc-700 active:scale-[0.96] text-zinc-300 hover:text-amber-400 rounded-lg text-xs font-mono border border-white/[0.08] transition flex items-center space-x-1.5 disabled:opacity-50"
                      title="Audition Voice Sample"
                    >
                      {isAuditioning ? (
                        <span className="playing-bars">
                          <span />
                          <span />
                          <span />
                        </span>
                      ) : (
                        <Volume2 className="w-3 h-3 text-amber-400" />
                      )}
                      <span className="text-[10px]">
                        {isAuditioning ? 'Playing' : 'Audition'}
                      </span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
