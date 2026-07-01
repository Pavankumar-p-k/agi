import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthProvider, useAuth } from '../lib/auth';
import type { ReactNode } from 'react';

const mockPush = vi.fn();
const mockReplace = vi.fn();
let mockPathname = '/';

vi.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
}));

beforeEach(() => {
  localStorage.clear();
  mockPush.mockClear();
  mockReplace.mockClear();
  mockPathname = '/';
});

function TestConsumer() {
  const { token, username, isAuthenticated, login, logout, isLoading } = useAuth();
  if (isLoading) return <div data-testid="loading">Loading auth...</div>;
  return (
    <div>
      <div data-testid="auth-status">{isAuthenticated ? 'logged-in' : 'logged-out'}</div>
      {token && <div data-testid="token">{token}</div>}
      {username && <div data-testid="username">{username}</div>}
      <button data-testid="login-btn" onClick={() => login('12345', '123456').catch(() => {})}>Login</button>
      <button data-testid="logout-btn" onClick={logout}>Logout</button>
    </div>
  );
}

function renderWithAuth(ui: ReactNode) {
  return render(<AuthProvider>{ui}</AuthProvider>);
}

describe('AuthProvider', () => {
  it('shows logged-out state when no stored session', async () => {
    renderWithAuth(<TestConsumer />);
    await waitFor(() => expect(screen.getByTestId('auth-status')).toHaveTextContent('logged-out'));
  });

  it('restores session from localStorage', async () => {
    localStorage.setItem('j-token', 'saved-token');
    localStorage.setItem('j-username', 'saved-user');
    renderWithAuth(<TestConsumer />);
    await waitFor(() => expect(screen.getByTestId('auth-status')).toHaveTextContent('logged-in'));
    expect(screen.getByTestId('token')).toHaveTextContent('saved-token');
    expect(screen.getByTestId('username')).toHaveTextContent('saved-user');
  });

  it('logs in with dev credentials (12345/123456)', async () => {
    renderWithAuth(<TestConsumer />);
    await waitFor(() => expect(screen.getByTestId('auth-status')).toHaveTextContent('logged-out'));
    const user = userEvent.setup();
    await user.click(screen.getByTestId('login-btn'));
    await waitFor(() => expect(screen.getByTestId('auth-status')).toHaveTextContent('logged-in'));
    expect(screen.getByTestId('token')).toHaveTextContent('dev-token');
  });

  it('logs out and redirects to /auth/login', async () => {
    localStorage.setItem('j-token', 'saved-token');
    localStorage.setItem('j-username', 'saved-user');
    renderWithAuth(<TestConsumer />);
    await waitFor(() => expect(screen.getByTestId('auth-status')).toHaveTextContent('logged-in'));
    const user = userEvent.setup();
    await user.click(screen.getByTestId('logout-btn'));
    expect(screen.getByTestId('auth-status')).toHaveTextContent('logged-out');
    expect(localStorage.getItem('j-token')).toBeNull();
    expect(mockPush).toHaveBeenCalledWith('/auth/login');
  });

  it('redirects unauthenticated users away from private paths', async () => {
    mockPathname = '/operations';
    renderWithAuth(<TestConsumer />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/auth/login'));
  });

  it('does not redirect on public paths', async () => {
    mockPathname = '/auth/login';
    renderWithAuth(<TestConsumer />);
    await waitFor(() => expect(screen.getByTestId('auth-status')).toHaveTextContent('logged-out'));
    expect(mockReplace).not.toHaveBeenCalled();
  });
});

describe('LoginPage', () => {
  it('redirects to / when already authenticated', async () => {
    localStorage.setItem('j-token', 'existing-token');
    const { default: LoginPage } = await import('../app/auth/login/page');
    renderWithAuth(<LoginPage />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/'));
  });
});
