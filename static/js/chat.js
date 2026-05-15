'use strict';

import { highlightKeywords } from './utils.js';

let chatMsgs;

export function initChat() {
  chatMsgs = document.getElementById('chat-messages');
}

export function addMsg(role, text, kws) {
  if (!chatMsgs) initChat();
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.innerHTML = `
    <div class="msg-role">${role==='user'?'you':'jarvis'}</div>
    <div class="msg-body">${highlightKeywords(text, kws || [])}</div>
  `;
  chatMsgs.appendChild(div);
  chatMsgs.scrollTop = chatMsgs.scrollHeight;
  return div;
}

export function addThinking() {
  if (!chatMsgs) initChat();
  const div = document.createElement('div');
  div.className = 'msg jarvis';
  div.id = 'thinking-msg';
  div.innerHTML = `<div class="msg-role">jarvis</div><div class="msg-body dots"><span>●</span><span>●</span><span>●</span></div>`;
  chatMsgs.appendChild(div);
  chatMsgs.scrollTop = chatMsgs.scrollHeight;
}

export function removeThinking() {
  const el = document.getElementById('thinking-msg');
  if (el) el.remove();
}
