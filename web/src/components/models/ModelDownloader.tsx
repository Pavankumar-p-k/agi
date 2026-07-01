'use client';

import { useState } from 'react';
import { api, type SetupStatus } from '@/lib/api';

/* ── Recommended Models (by hardware tier) ── */

const MODEL_RECOMMENDATIONS: Record<string, { id: string; name: string; size_gb: number; ram_min_gb: number; description: string }[]> = {
  low: [
    { id: 'llama3.2:3b', name: 'Llama 3.2 (3B)', size_gb: 2.0, ram_min_gb: 4, description: 'Fast, lightweight. Best for 4–8GB RAM.' },
    { id: 'phi3:3.8b', name: 'Phi-3 (3.8B)', size_gb: 2.3, ram_min_gb: 4, description: 'Microsoft\'s efficient small model.' },
  ],
  medium: [
    { id: 'llama3.2:3b', name: 'Llama 3.2 (3B)', size_gb: 2.0, ram_min_gb: 4, description: 'Good balance of speed and quality.' },
    { id: 'qwen2.5:7b', name: 'Qwen 2.5 (7B)', size_gb: 4.4, ram_min_gb: 8, description: 'Strong reasoning, 8–16GB RAM.' },
  ],
  high: [
    { id: 'qwen2.5:7b', name: 'Qwen 2.5 (7B)', size_gb: 4.4, ram_min_gb: 8, description: 'Best all-rounder for 8GB+ GPUs.' },
    { id: 'llama3.1:8b', name: 'Llama 3.1 (8B)', size_gb: 4.9, ram_min_gb: 8, description: 'Meta\'s latest, strong general model.' },
    { id: 'mistral:7b', name: 'Mistral (7B)', size_gb: 4.1, ram_min_gb: 8, description: 'Fast and capable, great for coding.' },
  ],
};

function getTier(ramGb: number): string {
  if (ramGb < 6) return 'low';
  if (ramGb < 12) return 'medium';
  return 'high';
}

/* ── Download Progress ── */

interface DownloadState {
  phase: 'idle' | 'downloading' | 'done' | 'error';
  percent: number | null;
  message: string;
}

/* ── Component ── */

interface Props {
  status: SetupStatus | null;
}

export default function ModelDownloader({ status }: Props) {
  const [download, setDownload] = useState<DownloadState>({ phase: 'idle', percent: null, message: '' });

  const ramGb = status?.hardware?.ram_gb || 8;
  const tier = getTier(ramGb);
  const recommendations = MODEL_RECOMMENDATIONS[tier];
  const installedModels = status?.installed_models || [];
  const alreadyInstalled = (modelId: string) => installedModels.some(m => m.startsWith(modelId.split(':')[0]));

  const handleDownload = async (modelId: string) => {
    setDownload({ phase: 'downloading', percent: 0, message: `Starting download of ${modelId}...` });
    try {
      const result = await api.models.pull(modelId, (pct, statusMsg) => {
        setDownload(prev => ({
          ...prev,
          percent: pct,
          message: statusMsg || `Downloading... ${pct ?? ''}`,
        }));
      });
      if (result.success) {
        setDownload({ phase: 'done', percent: 100, message: `${modelId} is ready!` });
      } else {
        setDownload({ phase: 'error', percent: null, message: result.message || 'Download failed' });
      }
    } catch (err) {
      setDownload({
        phase: 'error',
        percent: null,
        message: err instanceof Error ? err.message : 'Download failed',
      });
    }
  };

  return (
    <div className="space-y-4">
      {/* Tier indicator */}
      <div className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>
        Detected: <span className="uppercase tracking-[0.12em]" style={{ color: 'var(--j-sky)' }}>{tier}</span> tier
        {' · '}{ramGb}GB RAM
        {status?.hardware?.gpu_name && <>{' · '}{status.hardware.gpu_name}</>}
      </div>

      {/* Recommendations */}
      <div className="space-y-2">
        {recommendations.map(m => {
          const installed = alreadyInstalled(m.id);
          return (
            <div
              key={m.id}
              className="flex items-center gap-3 px-4 py-3 transition-all"
              style={{
                border: `1px solid ${installed ? 'rgba(74,222,128,0.15)' : 'var(--j-border)'}`,
                borderRadius: 'var(--j-radius-md)',
                background: installed ? 'rgba(74,222,128,0.03)' : 'transparent',
              }}
            >
              {/* Status */}
              <div
                className="w-2 h-2 rounded-full shrink-0"
                style={{
                  background: installed
                    ? 'var(--j-green)'
                    : download.phase === 'downloading' ? 'var(--j-gold)'
                    : 'var(--j-text-muted)',
                  boxShadow: installed ? '0 0 6px rgba(74,222,128,0.5)' : 'none',
                }}
              />

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="text-sm font-mono" style={{ color: 'var(--j-text)' }}>
                  {m.name}
                </div>
                <div className="text-[10px] mt-0.5" style={{ color: 'var(--j-text-muted)' }}>
                  {m.description}
                </div>
              </div>

              {/* Size */}
              <div className="text-[10px] font-mono shrink-0" style={{ color: 'var(--j-text-dim)' }}>
                {m.size_gb}GB
              </div>

              {/* Action */}
              {installed ? (
                <span className="text-[9px] font-mono uppercase tracking-[0.12em]" style={{ color: 'var(--j-green)' }}>
                  Installed
                </span>
              ) : download.phase === 'downloading' ? (
                <span className="text-[9px] font-mono" style={{ color: 'var(--j-gold)' }}>
                  {download.percent != null ? `${download.percent.toFixed(0)}%` : '...'}
                </span>
              ) : (
                <button
                  onClick={() => handleDownload(m.id)}
                  disabled={false}
                  className="px-3 py-1.5 text-[9px] font-mono uppercase tracking-[0.12em] transition-all disabled:opacity-40"
                  style={{
                    border: '1px solid var(--j-sky)',
                    borderRadius: 'var(--j-radius-sm)',
                    color: 'var(--j-sky)',
                    background: 'rgba(var(--j-sky-rgb),0.08)',
                  }}
                >
                  Download
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      {download.phase === 'downloading' && download.percent != null && (
        <div>
          <div className="h-1.5 w-full rounded-full overflow-hidden" style={{ background: 'rgba(var(--j-bg-rgb),0.5)' }}>
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${Math.min(download.percent, 100)}%`,
                background: 'var(--j-sky)',
                boxShadow: '0 0 8px rgba(0,210,255,0.4)',
              }}
            />
          </div>
          <div className="text-[9px] font-mono mt-1 text-center" style={{ color: 'var(--j-text-muted)' }}>
            {download.message}
          </div>
        </div>
      )}

      {/* Done / Error */}
      {download.phase === 'done' && (
        <div className="text-center py-2">
          <span className="text-[10px] font-mono" style={{ color: 'var(--j-green)' }}>
            ✓ {download.message}
          </span>
        </div>
      )}
      {download.phase === 'error' && (
        <div className="text-center py-2">
          <span className="text-[10px] font-mono" style={{ color: '#ff4757' }}>
            ✗ {download.message}
          </span>
          <button
            onClick={() => setDownload({ phase: 'idle', percent: null, message: '' })}
            className="ml-3 text-[9px] font-mono uppercase tracking-[0.12em] underline underline-offset-2"
            style={{ color: 'var(--j-sky)' }}
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
