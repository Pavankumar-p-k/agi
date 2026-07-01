'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useStreamingChat } from '@/hooks/useStreamingChat';
import { renderMarkdown } from '@/lib/md';
import VoiceInput from '@/components/chat/VoiceInput';
import ModelSelector from '@/components/chat/ModelSelector';
import FileUpload from '@/components/chat/FileUpload';
import PipelineIndicator from '@/components/chat/PipelineIndicator';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import { api } from '@/lib/api';

function fmtTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function ChatBubble({ role, text, time, isStreaming: streaming }: { role: string; text: string; time: number; isStreaming: boolean }) {
  const [copied, setCopied] = useState(false);
  const [reaction, setReaction] = useState<'up' | 'down' | null>(null);
  const isUser = role === 'user';

  const copy = useCallback(() => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [text]);

  return (
    <div className={`group flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center border font-mono text-xs font-bold"
        style={{
          background: isUser ? 'rgba(0,255,136,0.08)' : 'rgba(var(--j-sky-rgb),0.09)',
          color: isUser ? '#00ff88' : 'var(--j-sky)',
          borderColor: isUser ? 'rgba(0,255,136,0.22)' : 'var(--j-border-bright)',
        }}
      >
        {isUser ? 'U' : 'J'}
      </div>
      <div
        className={`relative max-w-[82%] border px-4 py-3 text-sm leading-relaxed ${isUser ? 'clip-hud' : ''}`}
        style={{
          background: isUser ? 'rgba(0,255,136,0.055)' : 'var(--j-surface)',
          borderColor: isUser ? 'rgba(0,255,136,0.18)' : 'var(--j-border)',
          color: 'var(--j-text)',
        }}
      >
        {!isUser && <div className="absolute left-0 top-0 h-full w-0.5 bg-[var(--j-sky)] shadow-[0_0_10px_var(--j-sky)]" />}
        <div className="prose prose-invert prose-sm max-w-none" dangerouslySetInnerHTML={{ __html: text ? renderMarkdown(text) : (streaming ? '▊' : '') }} />
        {streaming && text && <span className="animate-pulse text-[var(--j-sky)]">▊</span>}
        <div className="mt-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--j-text-muted)]">
          <span>{fmtTime(time)}</span>
          {role === 'assistant' && text && !streaming && (
            <>
              <button onClick={copy} className="opacity-0 transition-opacity hover:text-[var(--j-sky)] group-hover:opacity-100">{copied ? 'Copied' : 'Copy'}</button>
              <button onClick={() => setReaction(reaction === 'up' ? null : 'up')} className={`transition-opacity hover:text-[var(--j-sky)] ${reaction === 'up' ? 'opacity-100 text-[var(--j-sky)]' : 'opacity-0 group-hover:opacity-100'}`}>Up</button>
              <button onClick={() => setReaction(reaction === 'down' ? null : 'down')} className={`transition-opacity hover:text-[#ff4757] ${reaction === 'down' ? 'opacity-100 text-[#ff4757]' : 'opacity-0 group-hover:opacity-100'}`}>Down</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { messages, conversations, activeConvId, isConnected, isStreaming, isWaiting, send, clear, loadConversation, deleteConversation, renameConversation, clearAllConversations } = useStreamingChat();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const renameRef = useRef<HTMLInputElement>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renamingText, setRenamingText] = useState('');

  const filteredConvs = searchQuery
    ? conversations.filter(c => c.title.toLowerCase().includes(searchQuery.toLowerCase()))
    : conversations;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const queued = localStorage.getItem('jarvis:queuedPrompt');
    if (!queued) return;
    localStorage.removeItem('jarvis:queuedPrompt');
    send(queued);
  }, [send]);

  const handleSend = () => {
    const el = inputRef.current;
    if (!el || !el.value.trim() || isStreaming) return;
    send(el.value.trim());
    el.value = '';
    el.style.height = 'auto';
  };

  const handleKey = (e: React.KeyboardEvent) => {
    const isCmdEnter = (e.metaKey || e.ctrlKey) && e.key === 'Enter';
    if (e.key === 'Enter' && !e.shiftKey && !isCmdEnter) {
      e.preventDefault();
      handleSend();
    }
    if (isCmdEnter) {
      const el = e.currentTarget as HTMLTextAreaElement;
      const start = el.selectionStart;
      el.value = el.value.slice(0, start) + '\n' + el.value.slice(el.selectionEnd);
      el.selectionStart = el.selectionEnd = start + 1;
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 200) + 'px';
    }
  };

  const startRename = (id: string, currentTitle: string) => {
    setRenamingId(id);
    setRenamingText(currentTitle);
    setTimeout(() => renameRef.current?.select(), 50);
  };

  const commitRename = () => {
    if (renamingId && renamingText.trim()) renameConversation(renamingId, renamingText.trim());
    setRenamingId(null);
  };

  const exportConv = useCallback((conv: { title: string; messages: { role: string; text: string; time: number }[] }) => {
    const lines = conv.messages.map(m => `[${new Date(m.time).toLocaleString()}] ${m.role === 'user' ? 'You' : 'JARVIS'}:\n${m.text}\n`).join('\n---\n\n');
    const blob = new Blob([`# ${conv.title}\n\n${lines}`], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${conv.title.replace(/[^a-zA-Z0-9]/g, '_').slice(0, 50)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const isLastStreaming = messages[messages.length - 1]?.id === '__stream__';
  const totalChars = messages.reduce((sum, m) => sum + m.text.length, 0);
  const estTokens = Math.round(totalChars / 4);
  const contextPct = Math.min((estTokens / 8192) * 100, 100);

  const HistoryPanel = ({ mobile = false }: { mobile?: boolean }) => (
    <div className={`${mobile ? 'h-full w-[290px]' : 'hidden w-[260px] md:flex'} flex-col border-r border-[var(--j-border)] bg-[rgba(var(--j-surface-rgb),0.78)] p-3 backdrop-blur-xl`}>
      <div className="mb-3 flex items-center justify-between px-1">
        <div className="hud-label">History</div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-[var(--j-text-muted)]">{conversations.length}</span>
          {conversations.length > 0 && <button onClick={clearAllConversations} className="font-mono text-[9px] uppercase tracking-[0.12em] text-[var(--j-text-muted)] hover:text-[#ff4757]">Clear</button>}
        </div>
      </div>
      <input value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Search conversations..." className="hud-input mb-3 w-full px-3 py-2 font-mono text-[11px]" />
      <input ref={renameRef} value={renamingText} onChange={(e) => setRenamingText(e.target.value)} onBlur={commitRename} onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setRenamingId(null); }} className="absolute -top-96 left-0 h-0 w-0" />
      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto">
        {filteredConvs.length === 0 ? (
          <p className="py-8 text-center font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--j-text-muted)]">{searchQuery ? 'No matches' : 'No conversations'}</p>
        ) : filteredConvs.map(c => {
          const active = activeConvId === c.id;
          return (
            <div key={c.id} onClick={() => { loadConversation(c.id); if (mobile) setShowHistory(false); }} className="group border px-3 py-2 text-[11px] transition-all" style={{ borderColor: active ? 'var(--j-border-bright)' : 'transparent', background: active ? 'rgba(var(--j-sky-rgb),0.08)' : 'transparent', color: active ? 'var(--j-sky)' : 'var(--j-text-dim)' }}>
              {renamingId === c.id ? (
                <input value={renamingText} onChange={(e) => setRenamingText(e.target.value)} onBlur={commitRename} onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setRenamingId(null); }} className="hud-input w-full px-2 py-1 text-[11px]" autoFocus />
              ) : <div className="truncate font-medium">{c.title}</div>}
              <div className="mt-1 flex items-center justify-between font-mono text-[9px] uppercase tracking-[0.12em] opacity-60">
                <span>{new Date(c.updatedAt).toLocaleDateString()}</span>
                <span className="flex gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                  <button onClick={(e) => { e.stopPropagation(); startRename(c.id, c.title); }}>Rename</button>
                  <button onClick={(e) => { e.stopPropagation(); exportConv(c); }}>Export</button>
                  <button onClick={(e) => { e.stopPropagation(); deleteConversation(c.id); }}>Delete</button>
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="hud-page -m-4 flex h-[calc(100vh-5.75rem)] flex-col overflow-hidden md:-m-6">
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-[var(--j-border)] bg-[rgba(var(--j-bg-rgb),0.78)] px-4 py-3 backdrop-blur-xl md:px-6">
        <button onClick={() => setShowHistory(true)} className="hud-icon-button h-9 w-9 md:hidden">☰</button>
        <div className="mr-auto">
          <div className="hud-label">AI Core</div>
          <div className="font-display text-3xl tracking-[0.12em]">Chat Interface</div>
        </div>
        <div className="hidden items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--j-text-dim)] sm:flex">
          <div className="h-1.5 w-24 bg-[var(--j-border)]"><div className="h-full bg-[var(--j-sky)]" style={{ width: `${contextPct}%` }} /></div>
          {estTokens} tokens
        </div>
        <Badge variant={isConnected ? 'new' : 'hot'}>{isConnected ? 'Connected' : 'Offline'}</Badge>
        <ModelSelector value="auto" onChange={async (m) => { try { await api.settings.update('model', { primary: m }); } catch (e) { console.warn('[Chat] model update failed', e); } }} />
        <Button variant="ghost" size="sm" onClick={clear}>New Chat</Button>
      </div>

      {showHistory && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowHistory(false)} />
          <div className="relative z-[1] h-full"><HistoryPanel mobile /></div>
        </div>
      )}

      <div className="min-h-0 flex flex-1 overflow-hidden">
        <HistoryPanel />
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-5">
            {messages.length === 0 && (
              <div className="flex h-full items-center justify-center text-center">
                <div className="max-w-xl">
                  <div className="hud-title text-6xl">JARVIS <span className="text-[var(--j-sky)]">ONLINE</span></div>
                  <p className="mt-4 text-sm leading-7 text-[var(--j-text-dim)]">Ask for code, research, automation, planning, debugging, or system control.</p>
                  <div className="mt-8 flex flex-wrap justify-center gap-2">
                    {['What can you do?', 'Write a Python script', 'Analyze this project'].map(ex => (
                      <button key={ex} onClick={() => send(ex)} className="clip-hud border border-[var(--j-border)] bg-[var(--j-surface)] px-4 py-3 font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--j-text-dim)] transition-all hover:border-[var(--j-sky)] hover:text-[var(--j-sky)]">{ex}</button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <AnimatePresence initial={false}>
              {messages.map(m => (
                <motion.div key={m.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
                  <ChatBubble role={m.role} text={m.text} time={m.time} isStreaming={m.id === '__stream__'} />
                </motion.div>
              ))}
            </AnimatePresence>

            {(isWaiting || (isStreaming && !isLastStreaming)) && (
              <div className="flex gap-3">
                <div className="flex h-8 w-8 items-center justify-center border border-[var(--j-border-bright)] bg-[rgba(var(--j-sky-rgb),0.09)] font-mono text-xs text-[var(--j-sky)]">J</div>
                <div className="flex-1 max-w-[82%]">
                  <PipelineIndicator phase={isWaiting ? 'waiting' : 'streaming'} />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="shrink-0 border-t border-[var(--j-border)] bg-[rgba(var(--j-bg-rgb),0.76)] px-4 py-3 backdrop-blur-xl">
            <div className="mx-auto flex max-w-4xl items-end gap-2">
              <FileUpload onFileProcessed={send} disabled={isStreaming} />
              <VoiceInput onTranscript={send} disabled={isStreaming} />
              <div className="flex flex-1 items-end gap-2 border border-[var(--j-border)] bg-[var(--j-surface)] px-3 py-2">
                <textarea
                  ref={inputRef}
                  rows={1}
                  placeholder="Message JARVIS..."
                  onKeyDown={handleKey}
                  onInput={(e) => {
                    const el = e.currentTarget;
                    el.style.height = 'auto';
                    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
                  }}
                  className="max-h-[200px] flex-1 resize-none border-none bg-transparent text-sm leading-relaxed outline-none"
                  style={{ color: 'var(--j-text)', fontFamily: 'var(--j-font-active, var(--j-font-sans))' }}
                />
              </div>
              <Button variant="primary" onClick={handleSend} disabled={isStreaming}>Send</Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
