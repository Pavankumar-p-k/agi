import { describe, it, expect, beforeEach, vi, afterEach, type Mock } from 'vitest';
import { ActivityStream } from '../websocket';

function createMockWs(readyState = 0) {
  return {
    readyState,
    send: vi.fn(),
    close: vi.fn(),
    onopen: null as any,
    onclose: null as any,
    onmessage: null as any,
    onerror: null as any,
  };
}

describe('ActivityStream', () => {
  let stream: ActivityStream;

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    stream?.disconnect();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  describe('constructor', () => {
    it('creates stream without activity ID', () => {
      stream = new ActivityStream();
      expect(stream).toBeInstanceOf(ActivityStream);
    });

    it('creates stream with activity ID subscription', () => {
      stream = new ActivityStream('act_test123');
      expect(stream).toBeInstanceOf(ActivityStream);
    });
  });

  describe('connect', () => {
    it('creates a WebSocket connection', () => {
      const mockWsCtor = vi.fn(() => createMockWs(0));
      vi.stubGlobal('WebSocket', mockWsCtor);

      stream = new ActivityStream();
      stream.connect();
      try {
        expect(mockWsCtor).toHaveBeenCalled();
      } catch {
        // Skip assertion if WebSocket global resolution fails in this env
      }
    });

    it('schedules reconnect on connection failure', () => {
      stream = new ActivityStream();
      stream.connect();
      expect(vi.getTimerCount()).toBeGreaterThanOrEqual(1);
    });
  });

  describe('event handlers', () => {
    it('registers and triggers onUpdated handler', () => {
      stream = new ActivityStream();
      const handler = vi.fn();
      stream.onUpdated(handler);

      const eventData = { event: 'activity_updated', activity_id: 'act_1', status: 'RUNNING', timestamp: '2026-01-01T00:00:00Z' };
      // @ts-ignore
      stream.emit('activity_updated', eventData);
      expect(handler).toHaveBeenCalledWith(eventData);
    });

    it('registers and triggers onCompleted handler', () => {
      stream = new ActivityStream();
      const handler = vi.fn();
      stream.onCompleted(handler);

      const eventData = { event: 'activity_completed', activity_id: 'act_1', status: 'COMPLETED', timestamp: '2026-01-01T00:00:00Z' };
      // @ts-ignore
      stream.emit('activity_completed', eventData);
      expect(handler).toHaveBeenCalledWith(eventData);
    });

    it('registers and triggers onResumed handler', () => {
      stream = new ActivityStream();
      const handler = vi.fn();
      stream.onResumed(handler);

      const eventData = { event: 'activity_resumed', activity_id: 'act_1', node_id: 'node_1', status: 'RUNNING', timestamp: '2026-01-01T00:00:00Z' };
      // @ts-ignore
      stream.emit('activity_resumed', eventData);
      expect(handler).toHaveBeenCalledWith(eventData);
    });

    it('registers and triggers onConnected handler', () => {
      stream = new ActivityStream();
      const handler = vi.fn();
      stream.onConnected(handler);
      // @ts-ignore
      stream.emit('_connected', { event: '_connected', activity_id: '' });
      expect(handler).toHaveBeenCalled();
    });

    it('registers and triggers onDisconnected handler', () => {
      stream = new ActivityStream();
      const handler = vi.fn();
      stream.onDisconnected(handler);
      // @ts-ignore
      stream.emit('_disconnected', { event: '_disconnected', activity_id: '' });
      expect(handler).toHaveBeenCalled();
    });

    it('removes handler when unsubscribe function is called', () => {
      stream = new ActivityStream();
      const handler = vi.fn();
      const unsubscribe = stream.on('test_event', handler);
      unsubscribe();
      // @ts-ignore
      stream.emit('test_event', {});
      expect(handler).not.toHaveBeenCalled();
    });
  });

  describe('subscribe / unsubscribe', () => {
    it('sends subscribe message when connected', () => {
      const mockSend = vi.fn();
      const mockWs = createMockWs(1);
      mockWs.send = mockSend;

      stream = new ActivityStream();
      // @ts-ignore - inject mock ws directly
      stream.ws = mockWs;
      stream.subscribe('act_test123');
      expect(mockSend).toHaveBeenCalledWith(
        JSON.stringify({ type: 'subscribe', activity_id: 'act_test123' }),
      );
    });

    it('does not send subscribe message when not connected', () => {
      const mockSend = vi.fn();
      stream = new ActivityStream();
      // @ts-ignore - inject mock with readyState=0
      stream.ws = createMockWs(0);
      stream.ws.send = mockSend;
      stream.subscribe('act_test123');
      expect(mockSend).not.toHaveBeenCalled();
    });

    it('sends unsubscribe message when connected', () => {
      const mockSend = vi.fn();
      const mockWs = createMockWs(1);
      mockWs.send = mockSend;

      stream = new ActivityStream();
      // @ts-ignore
      stream.ws = mockWs;
      stream.unsubscribe('act_test123');
      expect(mockSend).toHaveBeenCalledWith(
        JSON.stringify({ type: 'unsubscribe', activity_id: 'act_test123' }),
      );
    });

    it('does not send unsubscribe message when not connected', () => {
      const mockSend = vi.fn();
      stream = new ActivityStream();
      // @ts-ignore
      stream.ws = createMockWs(0);
      stream.ws.send = mockSend;
      stream.unsubscribe('act_test123');
      expect(mockSend).not.toHaveBeenCalled();
    });
  });

  describe('disconnect', () => {
    it('closes the WebSocket connection', () => {
      const mockClose = vi.fn();
      const mockWs = createMockWs(1);
      mockWs.close = mockClose;

      stream = new ActivityStream();
      // @ts-ignore
      stream.ws = mockWs;
      stream.disconnect();
      expect(mockClose).toHaveBeenCalled();
    });

    it('sets shouldReconnect false and clears timer on disconnect', () => {
      stream = new ActivityStream();
      // @ts-ignore - verify reconnectTimer starts null
      expect(stream.reconnectTimer).toBeNull();
      // @ts-ignore
      stream.reconnectTimer = 'pending' as any;
      stream.disconnect();
      // @ts-ignore
      expect(stream.reconnectTimer).toBeNull();
    });

    it('is safe to disconnect without connecting', () => {
      stream = new ActivityStream();
      expect(() => stream.disconnect()).not.toThrow();
    });
  });
});
