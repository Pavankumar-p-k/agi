const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || '';
const PROTO = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const HOST = typeof window !== 'undefined' ? window.location.host : '127.0.0.1:8000';
const BASE = WS_BASE || `${PROTO}//${HOST}`;

type WSMessage = Record<string, unknown>;
type Handler = (data: WSMessage) => void;

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('j-token');
}

export class WSClient {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<Handler>>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private url: string;

  constructor(path = '/ws/chat_stream') {
    const token = getToken();
    const query = token ? `?token=${encodeURIComponent(token)}` : '';
    this.url = `${BASE}${path}${query}`;
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws.onopen = () => this.emit('_connected', {});
    this.ws.onclose = () => {
      this.emit('_disconnected', {});
      this.ws = null;
      this.scheduleReconnect();
    };
    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        const type = (data.type as string) || '_message';
        this.emit(type, data);
        this.emit('_message', data);
      } catch { /* ignore */ }
    };
    this.ws.onerror = () => this.ws?.close();
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }

  send(msg: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  on(type: string, handler: Handler) {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type)!.add(handler);
    return () => this.handlers.get(type)?.delete(handler);
  }

  private emit(type: string, data: WSMessage) {
    this.handlers.get(type)?.forEach((h) => h(data));
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, 3000);
  }
}
