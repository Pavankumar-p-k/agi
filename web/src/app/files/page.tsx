'use client';

import { useEffect, useState, useRef } from 'react';
import Card from '@/components/ui/Card';
import { api } from '@/lib/api';

interface FileEntry {
  name: string;
  is_dir: boolean;
  size: number;
  modified: string;
}

function fmtSize(bytes: number): string {
  if (bytes === 0) return '-';
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (bytes >= 1024 && i < u.length - 1) { bytes /= 1024; i++; }
  return `${bytes.toFixed(1)} ${u[i]}`;
}

export default function FilesPage() {
  const [path, setPath] = useState('');
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentPath, setCurrentPath] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { loadFiles(); }, []);

  async function loadFiles(dir?: string) {
    setLoading(true);
    setError('');
    try {
      const res = await api.files.list(dir || currentPath);
      setEntries(res.entries || []);
      setCurrentPath(res.path || dir || '');
    } catch (e) {
      setError('Failed to load files');
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }

  function enterDir(name: string) {
    const newPath = currentPath ? `${currentPath}/${name}` : name;
    setHistory(prev => [...prev, currentPath]);
    loadFiles(newPath);
  }

  function goBack() {
    if (history.length === 0) return;
    const prev = history[history.length - 1];
    setHistory(prev => prev.slice(0, -1));
    loadFiles(prev);
  }

  async function uploadFile() {
    const input = fileRef.current;
    if (!input || !input.files?.length) return;
    const file = input.files[0];
    await api.files.upload(currentPath, file);
    input.value = '';
    loadFiles(currentPath);
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="font-display text-[28px] tracking-[0.12em] text-[var(--j-text)]">File Browser</h1>
      <p className="mt-1 text-xs text-[var(--j-text-dim)]">Browse and upload files</p>

      <div className="mt-6 flex items-center gap-3">
        <button onClick={goBack} disabled={history.length === 0} className="border border-[var(--j-border)] px-3 py-1.5 text-xs text-[var(--j-text)] hover:border-[var(--j-sky)] disabled:opacity-30">BACK</button>
        <span className="font-mono text-xs text-[var(--j-text-muted)]">/{currentPath}</span>
        <div className="ml-auto flex gap-3">
          <input ref={fileRef} type="file" className="hidden" onChange={uploadFile} />
          <button onClick={() => fileRef.current?.click()} className="border border-[var(--j-sky)] px-4 py-1.5 text-xs tracking-[0.12em] text-[var(--j-sky)] transition-colors hover:bg-[var(--j-sky)] hover:text-[var(--j-bg)]">UPLOAD</button>
        </div>
      </div>

      {error && <p className="mt-4 text-xs text-red-500">{error}</p>}

      {loading ? (
        <p className="mt-6 text-xs text-[var(--j-text-dim)]">Loading...</p>
      ) : entries.length === 0 ? (
        <p className="mt-6 text-xs text-[var(--j-text-dim)]">Empty directory.</p>
      ) : (
        <div className="mt-4 space-y-1">
          {entries.map(e => (
            <div
              key={e.name}
              onClick={() => e.is_dir && enterDir(e.name)}
              className={`flex items-center gap-4 border border-[var(--j-border)] bg-[var(--j-surface)] px-4 py-3 text-left transition-all ${e.is_dir ? 'cursor-pointer hover:border-[var(--j-sky)]' : ''}`}
            >
              <span className="text-sm text-[var(--j-text-dim)]">{e.is_dir ? '📁' : '📄'}</span>
              <span className="flex-1 text-sm text-[var(--j-text)]">{e.name}</span>
              <span className="font-mono text-[10px] text-[var(--j-text-muted)]">{fmtSize(e.size)}</span>
              <span className="font-mono text-[10px] text-[var(--j-text-muted)]">{new Date(e.modified).toLocaleDateString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
