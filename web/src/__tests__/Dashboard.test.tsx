import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import DashboardPage from '../app/page';

const mockStats = vi.fn();
const mockHealth = vi.fn();
const mockPlugins = vi.fn();
const mockDiagnostics = vi.fn().mockResolvedValue({
  status: 'ok', data: { environment: { ollama_available: true }, models: { 'qwen2.5:7b': {} } },
});

vi.mock('@/lib/api', () => ({
  api: {
    system: { stats: (...args: any[]) => mockStats(...args) },
    health: (...args: any[]) => mockHealth(...args),
    plugins: { list: (...args: any[]) => mockPlugins(...args) },
    diagnostics: { all: (...args: any[]) => mockDiagnostics(...args) },
  },
}));

vi.mock('@/components/ui/Card', () => ({
  default: ({ children, className, style, title }: any) =>
    <div data-testid="card" className={className} style={style}>{title && <div>{title}</div>}{children}</div>,
}));

vi.mock('@/components/ui/Pill', () => ({
  default: ({ children, color }: any) => <span data-testid="pill" data-color={color}>{children}</span>,
}));

vi.mock('@/components/ui/Badge', () => ({
  default: ({ children, color }: any) => <span data-testid="badge" data-color={color}>{children}</span>,
}));

vi.mock('@/components/ui/Button', () => ({
  default: ({ children, href, onClick, variant, ...props }: any) =>
    href ? <a data-testid="btn" data-variant={variant} href={href}>{children}</a>
         : <button data-testid="btn" data-variant={variant} onClick={onClick} {...props}>{children}</button>,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mockStats.mockResolvedValue({
    cpu: { percent: 45, count: 8 },
    memory: { total: 17179869184, available: 8589934592, percent: 50 },
    disk: { total: 512_000_000_000, used: 256_000_000_000, free: 256_000_000_000, percent: 50 },
    uptime_seconds: 3600,
    timestamp: new Date().toISOString(),
  });
  mockHealth.mockResolvedValue({ status: 'healthy', uptime: 3600, version: '1.0' });
  mockPlugins.mockResolvedValue({ plugins: [{ name: 'test-plugin' }] });
});

describe('DashboardPage', () => {
  it('renders hero section with JARVIS title and system status', async () => {
    render(<DashboardPage />);
    expect(await screen.findByText('JARVIS')).toBeInTheDocument();
    expect(screen.getByText('Just A Rather Very Intelligent System')).toBeInTheDocument();
    expect(screen.getByText('ONLINE')).toBeInTheDocument();
  });

  it('shows CPU stat from API', async () => {
    render(<DashboardPage />);
    expect(await screen.findByText('CPU Load')).toBeInTheDocument();
    expect(screen.getAllByText('45%').length).toBeGreaterThanOrEqual(1);
  });

  it('shows memory usage from API', async () => {
    render(<DashboardPage />);
    expect(await screen.findByText(/8\.0 GB \/ 16\.0 GB/)).toBeInTheDocument();
  });

  it('shows plugin count from API', async () => {
    render(<DashboardPage />);
    expect(await screen.findByText('1')).toBeInTheDocument();
    expect(screen.getByText('Active Plugins')).toBeInTheDocument();
  });

  it('shows OFFLINE when health fails', async () => {
    mockHealth.mockRejectedValue(new Error('unreachable'));
    render(<DashboardPage />);
    expect(await screen.findByText('OFFLINE')).toBeInTheDocument();
  });

  it('shows fallback dashes when stats fail', async () => {
    mockStats.mockRejectedValue(new Error('unreachable'));
    mockHealth.mockRejectedValue(new Error('unreachable'));
    mockPlugins.mockRejectedValue(new Error('unreachable'));
    render(<DashboardPage />);
    const dashes = await screen.findAllByText('--');
    expect(dashes.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('renders core module section', async () => {
    render(<DashboardPage />);
    expect(await screen.findByText('Architecture')).toBeInTheDocument();
    expect(screen.getByText('Module 01')).toBeInTheDocument();
    expect(screen.getByText('Module 02')).toBeInTheDocument();
  });

  it('renders action buttons', async () => {
    render(<DashboardPage />);
    expect(await screen.findAllByTestId('btn')).toHaveLength(3);
    const btns = screen.getAllByTestId('btn');
    expect(btns[0]).toHaveTextContent('Open Chat');
    expect(btns[1]).toHaveTextContent('CLI Mode');
    expect(btns[2]).toHaveTextContent('Monitor System');
  });
});
