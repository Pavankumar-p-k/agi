/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — WebSocket Client
 *
 * Typed WebSocket connection with auto-reconnect and event dispatch.
 * Supports subscribing to activity graph events by activity_id.
 * ─────────────────────────────────────────────────────────────────────────── */
import { getTokenForWs } from './client';
import type { ActivityEvent } from '../generated/types';

const WS_CONFIG = {
  reconnectDelay: 3000,
  maxReconnectDelay: 30000,
};

function getWsBase(): string {
  if (typeof window === 'undefined') return 'ws://127.0.0.1:8000';
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}`;
}

export class ActivityStream {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<(data: any) => void>>();
  private subscribed = new Set<string>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private shouldReconnect = true;
  private url: string;

  constructor(activityId?: string) {
    const base = getWsBase();
    const token = getTokenForWs();
    const params = new URLSearchParams();
    if (token) params.set('token', token);
    this.url = `${base}/api/activity/ws${params.toString() ? `?${params.toString()}` : ''}`;
    if (activityId) {
      this.subscribed.add(activityId);
    }
  }

  connect(): void {
    if (this.ws?.readyState === 1) return;
    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.emit('_connected', { event: '_connected', activity_id: '' });
      for (const id of this.subscribed) {
        this.ws?.send(JSON.stringify({ type: 'subscribe', activity_id: id }));
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as ActivityEvent;
        this.emit(data.event, data);
        this.emit('_message', data);
      } catch {
        // Ignore malformed messages
      }
    };

    this.ws.onclose = () => {
      this.emit('_disconnected', { event: '_disconnected', activity_id: '' });
      if (this.shouldReconnect) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror, triggering reconnect
    };
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  subscribe(activityId: string): void {
    this.subscribed.add(activityId);
    if (this.ws?.readyState === 1) {
      this.ws.send(JSON.stringify({ type: 'subscribe', activity_id: activityId }));
    }
  }

  unsubscribe(activityId: string): void {
    this.subscribed.delete(activityId);
    if (this.ws?.readyState === 1) {
      this.ws.send(JSON.stringify({ type: 'unsubscribe', activity_id: activityId }));
    }
  }

  on(event: string, handler: (data: any) => void): () => void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set());
    }
    this.handlers.get(event)!.add(handler);
    return () => {
      this.handlers.get(event)?.delete(handler);
    };
  }

  onUpdated(handler: (data: ActivityEvent & { status: string }) => void): () => void {
    return this.on('activity_updated', handler as (data: ActivityEvent) => void);
  }

  onCompleted(handler: (data: ActivityEvent & { status: string }) => void): () => void {
    return this.on('activity_completed', handler as (data: ActivityEvent) => void);
  }

  onResumed(handler: (data: ActivityEvent & { status: string }) => void): () => void {
    return this.on('activity_resumed', handler as (data: ActivityEvent) => void);
  }

  onConnected(handler: () => void): () => void {
    return this.on('_connected', () => handler());
  }

  onDisconnected(handler: () => void): () => void {
    return this.on('_disconnected', () => handler());
  }

  private emit(event: string, data: any): void {
    const handlers = this.handlers.get(event);
    if (handlers) {
      handlers.forEach((h) => h(data));
    }
  }

  private scheduleReconnect(): void {
    if (!this.shouldReconnect) return;
    const delay = Math.min(
      WS_CONFIG.reconnectDelay * Math.pow(1.5, this.reconnectAttempts),
      WS_CONFIG.maxReconnectDelay,
    );
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }
}
