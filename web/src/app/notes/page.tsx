'use client';

import { useEffect, useState } from 'react';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import { api } from '@/lib/api';

interface Note {
  id: number;
  title: string;
  content: string;
  tags: string[];
  updated_at: string;
}

interface Reminder {
  id: number;
  title: string;
  remind_at: string;
  repeat?: string;
}

export default function NotesPage() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<'notes' | 'reminders'>('notes');
  const [newTitle, setNewTitle] = useState('');
  const [newContent, setNewContent] = useState('');
  const [newRemindAt, setNewRemindAt] = useState('');
  const [newReminderTitle, setNewReminderTitle] = useState('');

  useEffect(() => {
    Promise.all([
      api.notes.list().catch(() => []),
      api.reminders.list().catch(() => []),
    ]).then(([n, r]) => {
      setNotes(n as Note[]);
      setReminders(r as Reminder[]);
    }).catch(() => setError('Failed to load')).finally(() => setLoading(false));
  }, []);

  async function createNote() {
    if (!newTitle.trim()) return;
    const n = await api.notes.create({ title: newTitle, content: newContent });
    setNotes(prev => [...prev, { id: n.id, title: n.title, content: newContent, tags: [], updated_at: new Date().toISOString() }]);
    setNewTitle('');
    setNewContent('');
  }

  async function deleteNote(id: number) {
    await api.notes.delete(id);
    setNotes(prev => prev.filter(n => n.id !== id));
  }

  async function createReminder() {
    if (!newReminderTitle.trim() || !newRemindAt) return;
    const r = await api.reminders.create({ title: newReminderTitle, remind_at: newRemindAt });
    setReminders(prev => [...prev, { id: r.id, title: r.title, remind_at: r.remind_at }]);
    setNewReminderTitle('');
    setNewRemindAt('');
  }

  async function deleteReminder(id: number) {
    await api.reminders.delete(id);
    setReminders(prev => prev.filter(r => r.id !== id));
  }

  if (loading) return <div className="p-8 text-[var(--j-text-dim)]">Loading...</div>;

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="font-display text-[28px] tracking-[0.12em] text-[var(--j-text)]">Notes & Reminders</h1>
      <p className="mt-1 text-xs text-[var(--j-text-dim)]">Manage your notes and reminders</p>

      <div className="mt-6 flex gap-4 border-b border-[var(--j-border)]">
        <button onClick={() => setTab('notes')} className={`pb-2 text-sm tracking-[0.1em] transition-colors ${tab === 'notes' ? 'text-[var(--j-sky)] border-b-2 border-[var(--j-sky)]' : 'text-[var(--j-text-dim)] hover:text-[var(--j-text)]'}`}>Notes ({notes.length})</button>
        <button onClick={() => setTab('reminders')} className={`pb-2 text-sm tracking-[0.1em] transition-colors ${tab === 'reminders' ? 'text-[var(--j-sky)] border-b-2 border-[var(--j-sky)]' : 'text-[var(--j-text-dim)] hover:text-[var(--j-text)]'}`}>Reminders ({reminders.length})</button>
      </div>

      {error && <p className="mt-4 text-xs text-red-500">{error}</p>}

      {tab === 'notes' && (
        <div className="mt-6 space-y-4">
          <div className="flex gap-3">
            <input value={newTitle} onChange={e => setNewTitle(e.target.value)} placeholder="Note title" className="flex-1 bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]" />
            <input value={newContent} onChange={e => setNewContent(e.target.value)} placeholder="Content (optional)" className="flex-1 bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]" />
            <button onClick={createNote} className="border border-[var(--j-sky)] px-4 py-2 text-xs tracking-[0.12em] text-[var(--j-sky)] transition-colors hover:bg-[var(--j-sky)] hover:text-[var(--j-bg)]">CREATE</button>
          </div>
          {notes.length === 0 ? (
            <p className="text-xs text-[var(--j-text-dim)]">No notes yet.</p>
          ) : (
            notes.map(n => (
              <Card key={n.id}>
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-display text-lg tracking-[0.08em] text-[var(--j-text)]">{n.title}</h3>
                    {n.content && <p className="mt-1 text-xs text-[var(--j-text-dim)] line-clamp-2">{n.content}</p>}
                    <div className="mt-2 flex flex-wrap gap-2">
                      {n.tags.map(t => <Badge key={t}>{t}</Badge>)}
                      <span className="text-[10px] text-[var(--j-text-muted)]">{new Date(n.updated_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <button onClick={() => deleteNote(n.id)} className="text-xs text-red-400 hover:text-red-300">DELETE</button>
                </div>
              </Card>
            ))
          )}
        </div>
      )}

      {tab === 'reminders' && (
        <div className="mt-6 space-y-4">
          <div className="flex gap-3">
            <input value={newReminderTitle} onChange={e => setNewReminderTitle(e.target.value)} placeholder="Reminder title" className="flex-1 bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]" />
            <input value={newRemindAt} onChange={e => setNewRemindAt(e.target.value)} type="datetime-local" className="bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]" />
            <button onClick={createReminder} className="border border-[var(--j-sky)] px-4 py-2 text-xs tracking-[0.12em] text-[var(--j-sky)] transition-colors hover:bg-[var(--j-sky)] hover:text-[var(--j-bg)]">CREATE</button>
          </div>
          {reminders.length === 0 ? (
            <p className="text-xs text-[var(--j-text-dim)]">No reminders yet.</p>
          ) : (
            reminders.map(r => (
              <Card key={r.id}>
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-display text-lg tracking-[0.08em] text-[var(--j-text)]">{r.title}</h3>
                    <p className="mt-1 text-xs text-[var(--j-gold)]">{new Date(r.remind_at).toLocaleString()}</p>
                    {r.repeat && <Badge variant="hot">{r.repeat}</Badge>}
                  </div>
                  <button onClick={() => deleteReminder(r.id)} className="text-xs text-red-400 hover:text-red-300">DELETE</button>
                </div>
              </Card>
            ))
          )}
        </div>
      )}
    </div>
  );
}
