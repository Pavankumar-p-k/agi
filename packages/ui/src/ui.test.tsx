import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { activity, analytics, chat, dashboard, knowledge, memory, projects } from '@jarvis/sdk';

describe('UI API client integration', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sends chat text through the SDK API client', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ response: 'Hello from JARVIS' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(chat.send('status update')).resolves.toEqual({ response: 'Hello from JARVIS' });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chat',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ message: 'status update' }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    );
  });
});

describe('Chat route', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.history.pushState({}, '', '/');
  });

  it('submits a message and renders the assistant response', async () => {
    window.history.pushState({}, '', '/chat');
    vi.spyOn(chat, 'send').mockResolvedValue({ response: 'I am ready.' });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <App />
      </QueryClientProvider>,
    );

    const composer = screen.getByRole('textbox', { name: 'Message JARVIS' });
    fireEvent.change(composer, { target: { value: 'Run diagnostics' } });
    fireEvent.submit(composer.closest('form')!);

    expect(await screen.findByText('Run diagnostics')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('I am ready.')).toBeInTheDocument());
    expect(chat.send).toHaveBeenCalledWith('Run diagnostics', expect.anything());
  });
});

describe('Workspace routes', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.history.pushState({}, '', '/');
  });

  describe('Operator overview pages', () => {
    afterEach(() => {
      vi.restoreAllMocks();
      window.history.pushState({}, '', '/');
    });

    it('renders dashboard metrics and monthly highlights as cards', async () => {
      window.history.pushState({}, '', '/dashboard');
      vi.spyOn(dashboard, 'stats').mockResolvedValue({ gpu_vram: '8 GB', gpu_pct: 42, memory_hot: 3, memory_cold: 8, search_queries: 12, commands: 5, reminders: 2, notes: 1, active_models: {} });
      vi.spyOn(dashboard, 'highlights').mockResolvedValue({ month: 'August 2026', conversations: 10, commands_executed: 5, searches: 12, reminders: 2, top_models: ['llama3'] });
      render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
      expect(await screen.findByText('GPU VRAM')).toBeInTheDocument();
      expect(screen.getByText('August 2026')).toBeInTheDocument();
      expect(screen.queryByText(/"gpu_vram"/)).not.toBeInTheDocument();
    });

    it('renders activity counts and an actionable activity row', async () => {
      window.history.pushState({}, '', '/activity');
      vi.spyOn(activity, 'counts').mockResolvedValue({ total: 1, running: 1, pending: 0, completed: 0, failed: 0, suspended: 0, cancelled: 0 });
      vi.spyOn(activity, 'list').mockResolvedValue([{ node_id: 'n1', activity_id: 'a1', node_type: 'goal', label: 'Ship release', status: 'RUNNING', depth: 0, parent_id: null, agent_id: 'agent-1', origin_node_id: null, artifacts: {}, workflow_id: null, started_at: null, completed_at: null, created_at: null, metadata: {} }]);
      vi.spyOn(activity, 'cancel').mockResolvedValue({ status: 'cancelled' });
      render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
      expect(await screen.findByText('Ship release')).toBeInTheDocument();
      expect(screen.getByText('Running')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    });

    it('renders analytics summaries without raw JSON', async () => {
      window.history.pushState({}, '', '/analytics');
      vi.spyOn(analytics, 'plannerPerformance').mockResolvedValue({ overall: { total_plans: 4, completed_plans: 3, successful: 2, failed: 1, success_rate: 0.667, avg_prediction_accuracy: 0.8 }, strategy_win_rates: [{ strategy: 'direct', total: 3, successful: 2, failed: 1, win_rate: 0.667 }], accuracy_trend: { direction: 'up', early_avg: 0.5, recent_avg: 0.8, recent: [] }, confidence_calibration: { status: 'good', avg_calibration_error: 0.1, buckets: [] }, duration_accuracy: { status: 'ok', avg_duration_error: 0, plans_with_duration_data: 0, significantly_wrong: 0 }, risk_accuracy: { high_risk_plans: 0, low_risk_plans: 0, high_risk_failure_rate: 0, low_risk_failure_rate: 0, risk_discrimination: 0, discrimination_quality: 'unknown' }, replan_metrics: { total_plans: 4, replanned_count: 1, replan_rate: 0.25, improved_after_replan: 1, avg_replans_per_plan: 0.25 }, failure_analysis: { total_failures: 1, patterns: [], common_reasons: [] }, computed_at: '2026-08-22T00:00:00Z' });
      render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
      expect(await screen.findByText('Success rate')).toBeInTheDocument();
      expect(screen.getByText('Strategy win rates')).toBeInTheDocument();
  });

  it('renders a useful memory empty state without raw JSON', async () => {
      window.history.pushState({}, '', '/memory');
      vi.spyOn(memory, 'list').mockResolvedValue([]);
      vi.spyOn(memory, 'stats').mockResolvedValue({ total: 0, total_entries: 0, vector_count: 0, episodic_count: 0, semantic_count: 0 });
      render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
      expect(await screen.findByText('No memory entries')).toBeInTheDocument();
    });
  });

  it('renders projects from the projects API and can create one', async () => {
    window.history.pushState({}, '', '/projects');
    vi.spyOn(projects, 'list').mockResolvedValue({ projects: [{ id: 'p1', name: 'Launch', status: 'active', description: 'Ship it' }] });
    vi.spyOn(projects, 'create').mockResolvedValue({ id: 'p2', name: 'New', status: 'active' });
    render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);

    expect(await screen.findByText('Launch')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: 'Project name' }), { target: { value: 'New' } });
    fireEvent.click(screen.getByRole('button', { name: '＋ Add project' }));
    await waitFor(() => expect(projects.create).toHaveBeenCalledWith({ name: 'New', description: undefined }));
  });

  it('searches knowledge through the API', async () => {
    window.history.pushState({}, '', '/knowledge');
    vi.spyOn(knowledge, 'statistics').mockResolvedValue({ total_knowledge_items: 1, total_experiences: 2, total_patterns: 3, total_failures: 4, knowledge_by_category: {}, domains: [] });
    vi.spyOn(knowledge, 'list').mockResolvedValue({ knowledge: [], total: 0 });
    vi.spyOn(knowledge, 'search').mockResolvedValue({ query: 'retry', total: 1, knowledge: [{ knowledge_id: 'k1', category: 'heuristic', claim: 'Retry transient errors', confidence: 0.9, evidence_count: 2, source_activity_ids: [], source_pattern_keys: [], tags: ['reliability'], created_at: null, last_validated: null, metadata: {} }] });
    render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);

    fireEvent.change(await screen.findByRole('textbox', { name: 'Search knowledge' }), { target: { value: 'retry' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    expect(await screen.findByText('Retry transient errors')).toBeInTheDocument();
    expect(knowledge.search).toHaveBeenCalledWith('retry', 50);
  });

  it('honestly reports unavailable backend routes', async () => {
    window.history.pushState({}, '', '/notes');
    render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
    expect(await screen.findByText('No notes')).toBeInTheDocument();
  });
});
