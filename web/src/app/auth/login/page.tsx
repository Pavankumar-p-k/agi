'use client';

import { useState, useCallback } from 'react';
import Button from '@/components/ui/Button';

const OAUTH_PROVIDERS = [
  { id: 'google', label: 'Google', icon: 'G' },
  { id: 'github', label: 'GitHub', icon: 'GH' },
];

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!username.trim()) { setError('Username is required'); return; }
    if (!password) { setError('Password is required'); return; }
    setLoading(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (res.ok && data.token) {
        localStorage.setItem('j-token', data.token);
        window.location.href = '/';
      } else {
        setError(data.detail || 'Invalid credentials');
      }
    } catch {
      setError('Could not connect to server');
    } finally {
      setLoading(false);
    }
  }, [username, password]);

  const oauthLogin = (provider: string) => {
    const api = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
    window.location.href = `${api}/auth/login/${provider}`;
  };

  return (
    <div className="relative -m-4 flex min-h-[calc(100vh-7rem)] items-center justify-center overflow-hidden p-5 md:-m-6">
      <div className="hud-grid absolute inset-0" />
      <div className="absolute left-1/2 top-[-260px] h-[720px] w-[720px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(var(--j-sky-rgb),0.12),transparent_68%)]" />
      <div className="relative z-[1] grid w-full max-w-5xl grid-cols-1 gap-px bg-[var(--j-border)] lg:grid-cols-[1.1fr_0.9fr]">
        <section className="bg-[rgba(var(--j-bg-rgb),0.9)] p-8 md:p-10">
          <div className="hud-label">Secure Access</div>
          <h1 className="hud-title mt-4 text-7xl md:text-8xl">JARVIS</h1>
          <p className="mt-5 max-w-md text-sm leading-7 text-[var(--j-text-dim)]">
            Authenticate into the local AI operating console. Sessions are stored locally and routed through the JARVIS auth layer.
          </p>
          <div className="mt-10 grid grid-cols-3 gap-px bg-[var(--j-border)]">
            {['AUTH', 'VAULT', 'LOCAL'].map(item => (
              <div key={item} className="bg-[var(--j-surface)] px-4 py-5 text-center font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--j-sky)]">
                {item}
              </div>
            ))}
          </div>
        </section>

        <section className="bg-[var(--j-surface)] p-8 md:p-10">
          <div className="mb-8 flex items-center gap-3">
            <span className="relative h-9 w-9 rotate-45 border border-[var(--j-sky)]">
              <span className="absolute left-1/2 top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 bg-[var(--j-sky)] shadow-[0_0_16px_var(--j-sky)]" />
            </span>
            <div>
              <div className="font-display text-3xl tracking-[0.14em]">ACCESS</div>
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--j-text-dim)]">Sign in to continue</div>
            </div>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <label className="block">
              <span className="hud-label mb-2 block">Username</span>
              <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Enter username" autoFocus className="hud-input w-full px-3 py-3 text-sm" />
            </label>
            <label className="block">
              <span className="hud-label mb-2 block">Password</span>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter password" className="hud-input w-full px-3 py-3 pr-16 text-sm" />
                <button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--j-sky)]">
                  {showPw ? 'Hide' : 'Show'}
                </button>
              </div>
            </label>
            {error && <div className="border border-[rgba(255,71,87,0.3)] bg-[rgba(255,71,87,0.08)] px-3 py-2 font-mono text-xs text-[#ff4757]">{error}</div>}
            <Button type="submit" disabled={loading} variant="primary" className="w-full">
              {loading ? 'Authenticating' : 'Sign In'}
            </Button>
          </form>

          <div className="my-6 flex items-center gap-3">
            <div className="h-px flex-1 bg-[var(--j-border)]" />
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--j-text-muted)]">or</span>
            <div className="h-px flex-1 bg-[var(--j-border)]" />
          </div>

          <div className="grid grid-cols-2 gap-2">
            {OAUTH_PROVIDERS.map(p => (
              <button key={p.id} onClick={() => oauthLogin(p.id)} className="clip-hud border border-[var(--j-border)] bg-[var(--j-bg)] px-3 py-3 font-mono text-xs uppercase tracking-[0.12em] text-[var(--j-text-dim)] transition-all hover:border-[var(--j-border-bright)] hover:text-[var(--j-sky)]">
                {p.icon} {p.label}
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
