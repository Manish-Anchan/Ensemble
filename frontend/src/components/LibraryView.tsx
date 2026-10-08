import React, { useEffect, useState } from 'react';
import { Disc3, Download, Play, RefreshCw, FileText } from 'lucide-react';

interface OutputTrack {
  filename: string;
  format: string;
  size_bytes: number;
  size_human: string;
  duration_human?: string;
  mtime: number;
  url: string;
}

export const LibraryView: React.FC = () => {
  const [tracks, setTracks] = useState<OutputTrack[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchTracks = async () => {
    setIsLoading(true);
    try {
      const resp = await fetch('/api/outputs');
      const data = await resp.json();
      setTracks(data.outputs || []);
    } catch (err) {
      console.error('Failed to load output tracks:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTracks();
  }, []);

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-white flex items-center space-x-2">
            <span>Mastered Audio Library</span>
            <span className="text-xs font-mono text-zinc-500 font-normal">
              ({tracks.length} produced tracks)
            </span>
          </h2>
          <p className="text-xs text-zinc-400 font-mono mt-0.5">
            All batch produced chapters, screenplays, and multi-cast masters stored in outputs/.
          </p>
        </div>

        <button
          onClick={fetchTracks}
          disabled={isLoading}
          className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 active:scale-[0.98] text-zinc-200 rounded-lg text-xs font-mono border border-white/[0.08] transition flex items-center space-x-1.5"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-amber-400' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Tracks Table */}
      <div className="bezel-outer overflow-hidden">
        <div className="bezel-inner overflow-hidden">
          {tracks.length === 0 ? (
            <div className="p-12 text-center flex flex-col items-center justify-center space-y-3">
              <Disc3 className="w-10 h-10 text-zinc-600" />
              <p className="text-sm font-semibold text-zinc-300">No Mastered Tracks Yet</p>
              <p className="text-xs text-zinc-500 font-mono max-w-sm">
                Run batch production via CLI (`make produce-ch`) or live stream a full chapter to generate master audio drama files.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-white/[0.06] bg-zinc-950/40 text-[11px] font-mono text-zinc-400">
                    <th className="p-4">Track Name</th>
                    <th className="p-4">Format</th>
                    <th className="p-4">File Size</th>
                    <th className="p-4">Last Modified</th>
                    <th className="p-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04] text-xs font-mono">
                  {tracks.map((track) => (
                    <tr
                      key={track.filename}
                      className="hover:bg-white/[0.02] transition-colors group"
                    >
                      <td className="p-4 text-zinc-200 font-medium font-sans">
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
                      <td className="p-4 text-zinc-400 uppercase font-mono text-[10px]">
                        <span className="px-2 py-0.5 rounded bg-zinc-800/80 border border-white/[0.06]">
                          {track.format}
                        </span>
                      </td>
                      <td className="p-4 text-zinc-400">{track.size_human}</td>
                      <td className="p-4 text-zinc-500">
                        {new Date(track.mtime * 1000).toLocaleDateString()}
                      </td>
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end space-x-2">
                          {track.format !== 'json' && (
                            <a
                              href={track.url}
                              target="_blank"
                              rel="noreferrer"
                              className="p-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 hover:text-amber-400 rounded-lg border border-white/[0.08] transition"
                              title="Play Track"
                            >
                              <Play className="w-3.5 h-3.5" />
                            </a>
                          )}
                          <a
                            href={track.url}
                            download
                            className="p-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 hover:text-amber-400 rounded-lg border border-white/[0.08] transition"
                            title="Download Track"
                          >
                            <Download className="w-3.5 h-3.5" />
                          </a>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
