'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { WSClient } from '@/lib/ws';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  time: number;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  updatedAt: number;
}

const STORAGE_KEY = 'j-conversations';

function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveConversations(convs: Conversation[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(convs));
  } catch { /* quota exceeded */ }
}

export function useStreamingChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>(loadConversations);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isWaiting, setIsWaiting] = useState(false);
  const wsRef = useRef<WSClient | null>(null);
  const streamTextRef = useRef('');
  const messagesRef = useRef<ChatMessage[]>([]);

  // keep ref in sync
  useEffect(() => { messagesRef.current = messages; }, [messages]);

  // persist conversations when they change
  useEffect(() => { saveConversations(conversations); }, [conversations]);

  // sync active conversation title
  useEffect(() => {
    if (!activeConvId || messages.length === 0) return;
    const first = messages.find(m => m.role === 'user');
    if (!first) return;
    const title = first.text.length > 60 ? first.text.slice(0, 60) + '…' : first.text;
    setConversations(prev => prev.map(c =>
      c.id === activeConvId ? { ...c, title, messages, updatedAt: Date.now() } : c
    ));
  }, [messages, activeConvId]);

  useEffect(() => {
    const ws = new WSClient();
    wsRef.current = ws;

    const unsub1 = ws.on('_connected', () => setIsConnected(true));
    const unsub2 = ws.on('_disconnected', () => setIsConnected(false));

    const unsub3 = ws.on('stream_token', (data) => {
      const token = data.token as string;
      const complete = data.complete as boolean;

      if (complete) {
        setIsStreaming(false);
        setIsWaiting(false);
        setMessages((prev) => {
          const finalText = streamTextRef.current;
          streamTextRef.current = '';
          return [...prev, { id: crypto.randomUUID(), role: 'assistant', text: finalText, time: Date.now() }];
        });
        return;
      }

      if (!isStreaming) {
        setIsStreaming(true);
        setIsWaiting(false);
        streamTextRef.current = '';
      }

      streamTextRef.current += token || '';
      setMessages((prev) => {
        const copy = [...prev];
        const last = copy[copy.length - 1];
        if (last?.role === 'assistant' && last.id === '__stream__') {
          copy[copy.length - 1] = { ...last, text: streamTextRef.current };
        } else {
          copy.push({ id: '__stream__', role: 'assistant', text: streamTextRef.current, time: Date.now() });
        }
        return copy;
      });
    });

    ws.connect();
    return () => {
      unsub1(); unsub2(); unsub3();
      ws.disconnect();
    };
  }, []);

  const send = useCallback((text: string) => {
    if (!text.trim() || !wsRef.current) return;
    setIsWaiting(true);
    const newMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', text, time: Date.now() };
    setMessages((prev) => [...prev, newMsg]);
    // create conversation on first message
    if (!activeConvId) {
      const conv: Conversation = {
        id: crypto.randomUUID(),
        title: text.length > 60 ? text.slice(0, 60) + '…' : text,
        messages: [],
        updatedAt: Date.now(),
      };
      setActiveConvId(conv.id);
      setConversations(prev => [conv, ...prev]);
    }
    wsRef.current.send({ type: 'chat', text });
  }, [activeConvId]);

  const clear = useCallback(() => {
    // save current to history before clearing
    setMessages([]);
    setActiveConvId(null);
  }, []);

  const loadConversation = useCallback((convId: string) => {
    const conv = conversations.find(c => c.id === convId);
    if (!conv) return;
    setMessages(conv.messages);
    setActiveConvId(convId);
  }, [conversations]);

  const deleteConversation = useCallback((convId: string) => {
    setConversations(prev => prev.filter(c => c.id !== convId));
    if (activeConvId === convId) {
      setMessages([]);
      setActiveConvId(null);
    }
  }, [activeConvId]);

  const renameConversation = useCallback((convId: string, title: string) => {
    setConversations(prev => prev.map(c =>
      c.id === convId ? { ...c, title, updatedAt: Date.now() } : c
    ));
  }, []);

  const clearAllConversations = useCallback(() => {
    setConversations([]);
    setMessages([]);
    setActiveConvId(null);
  }, []);

  return {
    messages, conversations, activeConvId,
    isConnected, isStreaming, isWaiting,
    send, clear, loadConversation, deleteConversation,
    renameConversation, clearAllConversations,
  };
}
