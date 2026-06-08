'use client';

import { useRef, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useToastStore } from '@/stores/toastStore';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

interface UploadedFile {
  name: string;
  size: number;
  type: string;
}

interface Props {
  onFileProcessed: (text: string) => void;
  disabled?: boolean;
}

export default function FileUpload({ onFileProcessed, disabled }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const addToast = useToastStore(s => s.addToast);

  const upload = useCallback(async (file: File) => {
    if (file.size > 50 * 1024 * 1024) {
      addToast('File too large (max 50 MB)', 'error');
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const token = localStorage.getItem('j-token');
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${API}/api/chat/upload`, {
        method: 'POST',
        headers,
        body: formData,
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || 'Upload failed');
      }

      const data = await res.json();
      const fileName = file.name.replace(/\.[^/.]+$/, '');
      const contextText = data.text || data.content || JSON.stringify(data);
      onFileProcessed(`[Attached: ${file.name}]\n\`\`\`\n${contextText.slice(0, 3000)}${contextText.length > 3000 ? '\n...' : ''}\n\`\`\``);
      addToast(`${file.name} uploaded`, 'success');
    } catch (e) {
      addToast(e instanceof Error ? e.message : 'Upload failed', 'error');
    } finally {
      setUploading(false);
    }
  }, [onFileProcessed, addToast]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) upload(file);
  }, [upload]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      upload(file);
      e.target.value = '';
    }
  }, [upload]);

  return (
    <>
      <input ref={inputRef} type="file" onChange={handleChange} className="hidden" />

      {/* Drag overlay */}
      <AnimatePresence>
        {dragOver && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onDragOver={(e) => e.preventDefault()}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className="absolute inset-0 z-40 flex items-center justify-center border border-[var(--j-border-bright)]"
            style={{ background: 'rgba(var(--j-sky-rgb),0.10)', backdropFilter: 'blur(8px)' }}
          >
            <div className="text-center">
              <div className="hud-title mb-2 text-5xl text-[var(--j-sky)]">UPLOAD</div>
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--j-text-dim)]">PDF, images, code, documents</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Upload button */}
      <motion.button
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.9 }}
        onClick={() => inputRef.current?.click()}
        disabled={disabled || uploading}
        title="Upload file"
        className="hud-icon-button h-10 w-10 shrink-0 disabled:opacity-30"
        style={{
          background: uploading ? 'rgba(56,189,248,0.1)' : 'var(--j-surface)',
          color: uploading ? 'var(--j-sky)' : 'var(--j-text-dim)',
          border: '1px solid var(--j-border)',
        }}
      >
        {uploading ? (
          <motion.span animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}>⟳</motion.span>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        )}
      </motion.button>
    </>
  );
}
