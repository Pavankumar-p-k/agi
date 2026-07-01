'use client';

import { useState, useEffect, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';

export default function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace('/');
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) return null;
  if (isAuthenticated) return null;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!username || !password) { setError('Username and password required'); return; }
    setError('');
    setSubmitting(true);
    try {
      await login(username, password);
      router.replace('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center">
      <div className="w-full max-w-sm border border-[var(--j-border)] bg-[var(--j-surface)] p-8">
        <div className="mb-8 text-center">
          <h1 className="font-display text-2xl tracking-[0.12em] text-[var(--j-text)]">
            JARVIS
          </h1>
          <p className="mt-1 text-xs tracking-[0.08em] text-[var(--j-text-dim)]">
            Neural OS
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            value={username}
            onChange={e => setUsername(e.target.value)}
            placeholder="Username"
            autoComplete="username"
            autoFocus
            className="w-full bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]"
          />
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Password"
            autoComplete="current-password"
            className="w-full bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]"
          />

          {error && (
            <p className="text-xs text-[#ff4757]">{error}</p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full border border-[var(--j-sky)] px-6 py-2 text-xs tracking-[0.12em] text-[var(--j-sky)] transition-colors hover:bg-[var(--j-sky)] hover:text-[var(--j-bg)] disabled:opacity-30"
          >
            {submitting ? 'SIGNING IN...' : 'SIGN IN'}
          </button>
        </form>
      </div>
    </div>
  );
}
