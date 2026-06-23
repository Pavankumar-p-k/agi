'use client';

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';

interface AuthContextValue {
  token: string | null;
  username: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextValue>({
  token: null,
  username: null,
  isAuthenticated: false,
  login: async () => {},
  logout: () => {},
  isLoading: true,
});

const PUBLIC_PATHS = new Set(['/', '/auth/login', '/_not-found', '/chat', '/voice', '/models', '/agents', '/automation', '/memory', '/skills', '/plugins', '/integrations', '/projects', '/media', '/files', '/notes', '/email', '/knowledge', '/diagnostics', '/settings', '/features']);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    const stored = localStorage.getItem('j-token');
    const storedUser = localStorage.getItem('j-username');
    if (stored) {
      setToken(stored);
      setUsername(storedUser);
    }
    setIsLoading(false);
  }, []);

  useEffect(() => {
    if (isLoading) return;
    if (token || PUBLIC_PATHS.has(pathname)) return;
    // Dev mode — no auth redirect
  }, [token, pathname, isLoading, router]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok || !data.token) {
      throw new Error(data.detail || 'Invalid credentials');
    }
    localStorage.setItem('j-token', data.token);
    localStorage.setItem('j-username', data.username || username);
    setToken(data.token);
    setUsername(data.username || username);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('j-token');
    localStorage.removeItem('j-username');
    setToken(null);
    setUsername(null);
    router.push('/auth/login');
  }, [router]);

  return (
    <AuthContext.Provider value={{ token, username, isAuthenticated: !!token, login, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
