'use client';

import { useEffect, useState } from 'react';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import { api } from '@/lib/api';

interface EmailStatus {
  configured: boolean;
  host?: string;
  user?: string;
}

interface EmailMessage {
  id?: string;
  subject?: string;
  from?: string;
  snippet?: string;
  [key: string]: unknown;
}

export default function EmailPage() {
  const [status, setStatus] = useState<EmailStatus | null>(null);
  const [messages, setMessages] = useState<EmailMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'inbox' | 'compose'>('inbox');
  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState('');
  const [selectedMsg, setSelectedMsg] = useState<EmailMessage | null>(null);
  const [draftInstruction, setDraftInstruction] = useState('');
  const [draftText, setDraftText] = useState('');

  useEffect(() => {
    Promise.all([
      api.emails.status(),
      api.emails.inbox(20).catch(() => ({ messages: [], count: 0 })),
    ]).then(([s, i]) => {
      setStatus(s);
      setMessages(i.messages as EmailMessage[]);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  async function send() {
    if (!to || !subject || !body) return;
    setSending(true);
    setSendResult('');
    try {
      const r = await api.emails.send(to, subject, body);
      setSendResult(r.sent ? 'Sent!' : 'Failed');
      if (r.sent) { setTo(''); setSubject(''); setBody(''); }
    } catch {
      setSendResult('Error sending');
    } finally {
      setSending(false);
    }
  }

  async function generateDraft() {
    if (!selectedMsg || !draftInstruction) return;
    const r = await api.emails.draft(selectedMsg, draftInstruction);
    setDraftText(r.draft);
  }

  if (loading) return <div className="p-8 text-[var(--j-text-dim)]">Loading...</div>;

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="font-display text-[28px] tracking-[0.12em] text-[var(--j-text)]">Email</h1>
      <p className="mt-1 text-xs text-[var(--j-text-dim)]">
        {status?.configured ? `Connected: ${status.user}@${status.host}` : 'Not configured — set EMAIL_HOST in env'}
      </p>

      <div className="mt-6 flex gap-4 border-b border-[var(--j-border)]">
        <button onClick={() => setTab('inbox')} className={`pb-2 text-sm tracking-[0.1em] transition-colors ${tab === 'inbox' ? 'text-[var(--j-sky)] border-b-2 border-[var(--j-sky)]' : 'text-[var(--j-text-dim)] hover:text-[var(--j-text)]'}`}>Inbox ({messages.length})</button>
        <button onClick={() => setTab('compose')} className={`pb-2 text-sm tracking-[0.1em] transition-colors ${tab === 'compose' ? 'text-[var(--j-sky)] border-b-2 border-[var(--j-sky)]' : 'text-[var(--j-text-dim)] hover:text-[var(--j-text)]'}`}>Compose</button>
      </div>

      {tab === 'inbox' && (
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            {messages.length === 0 ? (
              <p className="text-xs text-[var(--j-text-dim)]">Inbox empty.</p>
            ) : (
              messages.map((m, i) => (
                <button key={m.id || i} onClick={() => setSelectedMsg(m)} className={`w-full border border-[var(--j-border)] bg-[var(--j-surface)] px-4 py-3 text-left transition-all hover:border-[var(--j-sky)] ${selectedMsg?.id === m.id ? 'border-[var(--j-sky)]' : ''}`}>
                  <p className="text-sm text-[var(--j-text)]">{String(m.subject || '(no subject)')}</p>
                  <p className="text-[10px] text-[var(--j-text-dim)]">{String(m.from || '')}</p>
                  {m.snippet && <p className="mt-1 text-[10px] text-[var(--j-text-muted)] line-clamp-1">{String(m.snippet)}</p>}
                </button>
              ))
            )}
          </div>

          <div>
            {selectedMsg ? (
              <Card>
                <h3 className="font-display text-sm text-[var(--j-text)]">{String(selectedMsg.subject || '(no subject)')}</h3>
                <p className="mt-1 text-[10px] text-[var(--j-text-dim)]">From: {String(selectedMsg.from || '')}</p>
                <pre className="mt-3 text-xs text-[var(--j-text-dim)] whitespace-pre-wrap">{JSON.stringify(selectedMsg, null, 2)}</pre>

                <div className="mt-4 border-t border-[var(--j-border)] pt-4">
                  <input value={draftInstruction} onChange={e => setDraftInstruction(e.target.value)} placeholder="Reply instruction..." className="w-full bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]" />
                  <button onClick={generateDraft} className="mt-2 border border-[var(--j-sky)] px-4 py-1.5 text-xs tracking-[0.12em] text-[var(--j-sky)] hover:bg-[var(--j-sky)] hover:text-[var(--j-bg)]">DRAFT REPLY</button>
                  {draftText && (
                    <div className="mt-3 border border-[var(--j-border)] bg-[var(--j-bg)] p-3">
                      <p className="text-xs text-[var(--j-text)]">{draftText}</p>
                    </div>
                  )}
                </div>
              </Card>
            ) : (
              <p className="text-xs text-[var(--j-text-dim)]">Select a message to view.</p>
            )}
          </div>
        </div>
      )}

      {tab === 'compose' && (
        <div className="mt-6 max-w-xl space-y-4">
          <input value={to} onChange={e => setTo(e.target.value)} placeholder="To" className="w-full bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]" />
          <input value={subject} onChange={e => setSubject(e.target.value)} placeholder="Subject" className="w-full bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]" />
          <textarea value={body} onChange={e => setBody(e.target.value)} placeholder="Body" rows={8} className="w-full resize-none bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]" />
          <button onClick={send} disabled={sending} className="border border-[var(--j-sky)] px-6 py-2 text-xs tracking-[0.12em] text-[var(--j-sky)] transition-colors hover:bg-[var(--j-sky)] hover:text-[var(--j-bg)] disabled:opacity-30">{sending ? 'SENDING...' : 'SEND'}</button>
          {sendResult && <p className="text-xs text-[var(--j-gold)]">{sendResult}</p>}
        </div>
      )}
    </div>
  );
}
