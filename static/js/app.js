'use strict';

import { extractKeyword, iconForType } from './utils.js';
import { connectWS, onToken, onComplete, onError } from './ws.js';
import { initChat, addMsg, addThinking, removeThinking } from './chat.js';
import {
  initGraph, setOrbThinking, setOrbIdle, setOrbTargetIntensity,
  morphParticlesToImage, morphParticlesToOrbit, morphParticlesToThink,
  onNodeClick, getNodeCount, getTotalCount,
  addNodeAnimated, linkPair,
} from './graph.js';
import { initCards, clearCards, buildCard, setActiveCard } from './cards.js';
import { fetchAndSeedNodes } from './memory.js';
import { renderBlueprint, clearBlueprint } from './ui-engine.js';

let history = [];
let busy = false;

export function boot() {
  initChat();
  initGraph();
  initCards();

  tickClock();
  setInterval(tickClock, 1000);

  setupInput();
  connectWS('ws://localhost:8000/ws/chat_stream');
  setupNodeDetail();

  onToken(() => {});
  onComplete(() => {});
  onError((data) => { console.warn('WS error:', data); });

  onNodeClick((data, idx) => showNodeDetail(data, idx));

  setTimeout(fetchAndSeedNodes, 300);
  updateNodeCounter();
  setInterval(updateNodeCounter, 2000);
}

function updateNodeCounter() {
  const count = getNodeCount();
  const total = getTotalCount();
  const el = document.getElementById('intensity-display');
  if (el) {
    el.textContent = `NODES ${count} | ${total}`;
  }
}

function tickClock() {
  const el = document.getElementById('clock');
  if (!el) return;
  const n = new Date();
  const pad = v => String(v).padStart(2,'0');
  el.textContent = `${pad(n.getHours())}:${pad(n.getMinutes())}:${pad(n.getSeconds())}`;
}

function setupInput() {
  const promptInput = document.getElementById('prompt-input');
  const sendBtn     = document.getElementById('send-btn');
  if (!promptInput || !sendBtn) return;

  sendBtn.addEventListener('click', doSend);
  promptInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); doSend(); }
  });
}

function doSend() {
  const promptInput = document.getElementById('prompt-input');
  if (!promptInput) return;
  const t = promptInput.value.trim();
  if (!t || busy) return;
  promptInput.value = '';
  sendMessage(t);
}

export function sendFromCard(text) {
  if (!text || busy) return;
  sendMessage(text);
}

export async function sendMessage(userText) {
  if (busy || !userText.trim()) return;
  busy = true;

  const kw = extractKeyword(userText);

  addMsg('user', userText);
  history.push({ role: 'user', content: userText });
  setOrbThinking(true);
  morphParticlesToThink();

  if (kw) {
    const tag = document.getElementById('entity-tag');
    if (tag) {
      tag.textContent = '⬡ ' + kw.toUpperCase();
      tag.classList.add('on');
    }
    setTimeout(() => morphParticlesToImage(kw), 500);
  }

  addThinking();

  try {
    const res = await fetch('http://localhost:8000/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer dev'
      },
      body: JSON.stringify({
        message: userText,
        history: history.map(h => ({ role: h.role, content: h.content }))
      })
    });

    const data = await res.json();
    if (res.status !== 200) throw new Error(data.detail || 'API Error');

    let parsed = data;
    if (typeof data.response === 'string' && !data.cards) {
      parsed = {
        type: 'answer',
        message: data.response,
        brain_intensity: 0.3,
        cards: [{ type: 'answer', title: 'RESPONSE', icon: '◈', text: data.response }]
      };
    }

    history.push({ role: 'assistant', content: data.response || JSON.stringify(data) });

    removeThinking();
    setOrbThinking(false);
    routeResponse(parsed, userText);

    const respText = data.response || json.message || '';
    const userNode = addNodeAnimated({ type: 'chat', label: 'user', text: userText, source: 'conversation' });
    const asstNode = addNodeAnimated({ type: 'chat', label: 'assistant', text: respText, source: 'conversation' });
    linkPair(userNode.id, asstNode.id);

  } catch (err) {
    removeThinking();
    setOrbThinking(false);
    setOrbIdle();
    morphParticlesToOrbit();
    addMsg('jarvis', '⚠ Error: ' + err.message);
    clearCards();
    buildCard({ type: 'warning', icon: '⚠', title: 'ERROR', text: err.message }, 0);
    setTimeout(() => setActiveCard(0), 200);
  }

  busy = false;
}

function routeResponse(json, userText) {
  const type = json.type || 'answer';
  const kw   = json.keyword || extractKeyword(userText) || null;
  const intensity = json.brain_intensity ?? 0.4;

  setOrbTargetIntensity(intensity);

  const tag = document.getElementById('entity-tag');
  if (kw) {
    if (tag) {
      tag.textContent = '⬡ ' + kw.toUpperCase();
      tag.classList.add('on');
    }
    morphParticlesToImage(kw);
  } else {
    if (tag) tag.classList.remove('on');
    morphParticlesToOrbit();
  }

  addMsg('jarvis', json.message || '', json.highlight || []);

  const typeLabels = {
    answer: 'RESPONSE', options: 'OPTIONS', plan: 'ACTION PLAN',
    warning: 'WARNING', insight: 'INSIGHT', question: 'INPUT REQUIRED',
    flow: 'WORKFLOW',
  };
  const labelEl = document.getElementById('cards-type-label');
  if (labelEl) labelEl.textContent = typeLabels[type] || type.toUpperCase();

  clearCards();
  clearBlueprint();

  if (json.ui_blueprint) {
    renderBlueprint(json.ui_blueprint);
  } else if (json.cards && json.cards.length) {
    json.cards.forEach((c, i) => buildCard(c, i, i * 80));
    setTimeout(() => {
      setActiveCard(0);
      setOrbTargetIntensity(Math.max(0.1, intensity * 0.6));
    }, 400);
  } else {
    buildCard({
      type,
      icon: iconForType(type),
      title: typeLabels[type] || 'RESPONSE',
      text: json.message || '',
      highlight: json.highlight || [],
    }, 0);
    setTimeout(() => {
      setActiveCard(0);
      setOrbTargetIntensity(Math.max(0.1, intensity * 0.6));
    }, 400);
  }

  setTimeout(() => { setOrbTargetIntensity(0.05); }, 6000);
}

// ════════════════════════════════════════════════════════════
//  NODE DETAIL PANEL
// ════════════════════════════════════════════════════════════
function setupNodeDetail() {
  document.getElementById('node-detail-close')?.addEventListener('click', closeNodeDetail);
}

function showNodeDetail(data, idx) {
  const panel = document.getElementById('node-detail');
  const textEl = document.getElementById('node-detail-text');
  const typeEl = document.getElementById('node-detail-type');
  const metaEl = document.getElementById('node-detail-meta');
  const idxEl = document.getElementById('node-detail-idx');
  const tsEl = document.getElementById('node-detail-ts');

  if (!panel) return;

  if (textEl) textEl.textContent = data.text || data.message || JSON.stringify(data);
  if (typeEl) typeEl.textContent = (data.type || 'node').toUpperCase();
  if (idxEl) idxEl.textContent = `#${idx}`;
  if (tsEl) tsEl.textContent = data.timestamp || data.ts || '';

  if (metaEl) {
    metaEl.innerHTML = '';
    const fields = ['label', 'source', 'role', 'score', 'intent'];
    fields.forEach(f => {
      if (data[f] !== undefined && data[f] !== null) {
        const row = document.createElement('div');
        row.className = 'meta-row';
        row.innerHTML = `<span class="meta-label">${f}</span><span class="meta-value">${data[f]}</span>`;
        metaEl.appendChild(row);
      }
    });
  }

  panel.classList.add('open');
}

function closeNodeDetail() {
  const panel = document.getElementById('node-detail');
  if (panel) panel.classList.remove('open');
}

document.addEventListener('DOMContentLoaded', boot);
