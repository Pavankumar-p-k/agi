'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { activity, agents, ActivityStream } from '@jarvis/sdk';
import type { ActivityNode, Agent, ActivityEvent } from '@jarvis/sdk';

type StatusCounts = Record<string, number>;

const BASE_POLL_MS = 15000;
const MAX_POLL_MS = 120000;

export function useOperationsData() {
  const [activities, setActivities] = useState<ActivityNode[]>([]);
  const [agentList, setAgentList] = useState<Agent[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [counts, setCounts] = useState<StatusCounts>({});
  const streamRef = useRef<ActivityStream | null>(null);

  const mountedRef = useRef(true);
  const backoffRef = useRef(1);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Poll with exponential backoff ─────────────────────────────────────

  const poll = useCallback(async () => {
    if (!mountedRef.current) return;
    try {
      const [acts, agts] = await Promise.all([
        activity.list(),
        agents.list().catch(() => [] as Agent[]),
      ]);
      if (!mountedRef.current) return;
      setActivities(acts);
      setAgentList(agts);

      const c: StatusCounts = {};
      for (const a of acts) {
        c[a.status] = (c[a.status] || 0) + 1;
      }
      setCounts(c);
      setError(null);
      backoffRef.current = 1;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load operations data');
      backoffRef.current = Math.min(backoffRef.current * 2, MAX_POLL_MS / BASE_POLL_MS);
    }
    if (mountedRef.current) {
      setLoading(false);
      const ms = Math.min(BASE_POLL_MS * backoffRef.current, MAX_POLL_MS);
      pollTimerRef.current = setTimeout(poll, ms);
    }
  }, []);

  // ── Exposed refresh (reset backoff) ───────────────────────────────────

  const refresh = useCallback(async () => {
    backoffRef.current = 1;
    await poll();
  }, [poll]);

  // ── Initial data load (alias for type clarity) ────────────────────────

  const loadData = refresh;

  // ── Activity actions ──────────────────────────────────────────────────

  const pauseActivity = useCallback(async (id: string) => {
    try {
      await activity.pause(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to pause activity');
    }
  }, []);

  const resumeActivity = useCallback(async (id: string) => {
    try {
      await activity.resume(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to resume activity');
    }
  }, []);

  const cancelActivity = useCallback(async (id: string) => {
    try {
      await activity.cancel(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to cancel activity');
    }
  }, []);

  // ── WebSocket stream ──────────────────────────────────────────────────

  useEffect(() => {
    mountedRef.current = true;
    poll();

    const stream = new ActivityStream();
    streamRef.current = stream;

    stream.onUpdated((e) => {
      setActivities((prev) => {
        if (!('status' in e)) return prev;
        const updateNode = (nodes: ActivityNode[]): ActivityNode[] =>
          nodes.map((n) => {
            if (n.node_id === (e as any).node_id) {
              return { ...n, status: (e as any).status };
            }
            return n;
          });
        return updateNode(prev);
      });
      setActivities((prev) => {
        const c: StatusCounts = {};
        for (const a of prev) {
          c[a.status] = (c[a.status] || 0) + 1;
        }
        setCounts(c);
        return prev;
      });
    });

    stream.onCompleted((e) => {
      setEvents((prev) => [e as ActivityEvent, ...prev].slice(0, 100));
      backoffRef.current = 1;
    });

    stream.onResumed((e) => {
      setEvents((prev) => [e as ActivityEvent, ...prev].slice(0, 100));
    });

    stream.on('_message', (e) => {
      if (e.event === 'schedule_triggered' || e.event === 'schedule_failed') {
        setEvents((prev) => [e as ActivityEvent, ...prev].slice(0, 100));
      }
    });

    stream.connect();

    return () => {
      mountedRef.current = false;
      if (pollTimerRef.current !== null) clearTimeout(pollTimerRef.current);
      stream.disconnect();
    };
  }, [poll]);

  return {
    activities,
    agentList,
    events,
    counts,
    loading,
    error,
    pauseActivity,
    resumeActivity,
    cancelActivity,
    refresh: loadData,
  };
}
