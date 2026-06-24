'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { activity, agents, ActivityStream } from '@jarvis/sdk';
import type { ActivityNode, Agent, ActivityEvent } from '@jarvis/sdk';

type StatusCounts = Record<string, number>;

export function useOperationsData() {
  const [activities, setActivities] = useState<ActivityNode[]>([]);
  const [agentList, setAgentList] = useState<Agent[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [counts, setCounts] = useState<StatusCounts>({});
  const streamRef = useRef<ActivityStream | null>(null);

  // ── Initial data load ──────────────────────────────────────────────────

  const loadData = useCallback(async () => {
    try {
      const [acts, agts] = await Promise.all([
        activity.list().catch(() => []),
        agents.list().catch(() => []),
      ]);
      setActivities(acts);
      setAgentList(agts);

      // Compute counts
      const c: StatusCounts = {};
      for (const a of acts) {
        c[a.status] = (c[a.status] || 0) + 1;
      }
      setCounts(c);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load operations data');
    } finally {
      setLoading(false);
    }
  }, []);

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
    loadData();

    const stream = new ActivityStream();
    streamRef.current = stream;

    stream.onUpdated((e) => {
      setActivities((prev) => {
        if (!('status' in e)) return prev;
        // Update the matching node in-place
        const updateNode = (nodes: ActivityNode[]): ActivityNode[] =>
          nodes.map((n) => {
            if (n.node_id === (e as any).node_id) {
              return { ...n, status: (e as any).status };
            }
            return n;
          });
        return updateNode(prev);
      });
      // Recompute counts
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
      loadData(); // Refresh full list
    });

    stream.onResumed((e) => {
      setEvents((prev) => [e as ActivityEvent, ...prev].slice(0, 100));
    });

    // Catch all events — schedule_triggered, schedule_failed, etc.
    stream.on('_message', (e) => {
      if (e.event === 'schedule_triggered' || e.event === 'schedule_failed') {
        setEvents((prev) => [e as ActivityEvent, ...prev].slice(0, 100));
      }
    });

    stream.connect();

    // Polling fallback every 15s
    const pollInterval = setInterval(loadData, 15000);

    return () => {
      stream.disconnect();
      clearInterval(pollInterval);
    };
  }, [loadData]);

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
