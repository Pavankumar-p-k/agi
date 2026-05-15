'use strict';

let ws = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
const MAX_RECONNECT = 10;

const callbacks = {
  onToken: null,
  onComplete: null,
  onError: null,
  onOpen: null,
  onClose: null,
};

export function onToken(fn) { callbacks.onToken = fn; }
export function onComplete(fn) { callbacks.onComplete = fn; }
export function onError(fn) { callbacks.onError = fn; }
export function onOpen(fn) { callbacks.onOpen = fn; }
export function onClose(fn) { callbacks.onClose = fn; }

export function connectWS(url) {
  if (ws && ws.readyState === WebSocket.OPEN) return;
  const wsUrl = url || 'ws://localhost:8000/ws/chat_stream';

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      reconnectAttempts = 0;
      if (callbacks.onOpen) callbacks.onOpen();
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);

        if (data.type === 'stream_token') {
          if (callbacks.onToken) callbacks.onToken(data);
          if (data.complete && callbacks.onComplete) callbacks.onComplete(data);
        } else if (data.type === 'tier_status') {
          if (data.status === 'completed' && callbacks.onComplete) callbacks.onComplete(data);
        } else if (data.type === 'error') {
          if (callbacks.onError) callbacks.onError(data);
        }
      } catch (_) {}
    };

    ws.onerror = () => {
      if (callbacks.onError) callbacks.onError({ message: 'WebSocket error' });
    };

    ws.onclose = () => {
      if (callbacks.onClose) callbacks.onClose();
      if (reconnectAttempts < MAX_RECONNECT) {
        reconnectAttempts++;
        reconnectTimer = setTimeout(() => connectWS(wsUrl), 3000 * reconnectAttempts);
      }
    };
  } catch (err) {
    if (callbacks.onError) callbacks.onError({ message: err.message });
  }
}

export function sendWS(data) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data));
    return true;
  }
  return false;
}

export function disconnectWS() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  if (ws) {
    ws.onclose = null;
    ws.close();
    ws = null;
  }
}
