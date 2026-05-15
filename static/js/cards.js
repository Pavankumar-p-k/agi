'use strict';

import { highlightKeywords, iconForType } from './utils.js';
import { fireBurst } from './graph.js';

let cardsScroll;
let cardElements = [];
let activeCardIndex = 0;

export function initCards() {
  cardsScroll = document.getElementById('cards-scroll');
  if (!cardsScroll) return;

  window.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' && cardElements.length) {
      e.preventDefault();
      setActiveCard(activeCardIndex + 1);
    }
    if (e.key === 'ArrowUp' && cardElements.length) {
      e.preventDefault();
      setActiveCard(activeCardIndex - 1);
    }
  });

  cardsScroll.addEventListener('wheel', e => {
    e.preventDefault();
    if (e.deltaY > 0) setActiveCard(activeCardIndex + 1);
    else              setActiveCard(activeCardIndex - 1);
  }, { passive: false });

  let touchStartY = 0;
  cardsScroll.addEventListener('touchstart', e => {
    touchStartY = e.touches[0].clientY;
  }, { passive: true });
  cardsScroll.addEventListener('touchend', e => {
    const diff = touchStartY - e.changedTouches[0].clientY;
    if (Math.abs(diff) > 40) {
      if (diff > 0) setActiveCard(activeCardIndex + 1);
      else          setActiveCard(activeCardIndex - 1);
    }
  }, { passive: true });
}

export function getActiveCardIndex() {
  return activeCardIndex;
}

export function getCardElements() {
  return cardElements;
}

export function clearCards() {
  if (!cardsScroll) return;
  cardsScroll.innerHTML = '';
  cardElements = [];
  activeCardIndex = 0;
  updateScrollDots();
}

export function buildCard(cfg, index, delay) {
  if (!cardsScroll) return null;
  delay = delay || 0;
  const el = document.createElement('div');
  el.className = 'card';
  el.dataset.type = cfg.type || 'answer';
  el.style.animationDelay = delay + 'ms';

  const head = document.createElement('div');
  head.className = 'card-head';

  const icon = document.createElement('div');
  icon.className = 'card-icon';
  icon.textContent = cfg.icon || iconForType(cfg.type);

  const title = document.createElement('div');
  title.className = 'card-title';
  title.textContent = cfg.title || (cfg.type ? cfg.type.toUpperCase() : 'INFO');

  head.append(icon, title);
  el.appendChild(head);

  if (cfg.text) {
    const body = document.createElement('div');
    body.className = 'card-text';
    body.innerHTML = highlightKeywords(cfg.text, cfg.highlight || []);
    el.appendChild(body);
  }

  if (cfg.options && cfg.options.length) {
    const opts = document.createElement('div');
    opts.className = 'card-options';
    cfg.options.forEach(opt => {
      const btn = document.createElement('button');
      btn.className = 'opt-btn';
      btn.innerHTML = `<span class="opt-icon">${opt.icon || '▸'}</span>${opt.label}`;
      btn.addEventListener('click', () => {
        opts.querySelectorAll('.opt-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        setTimeout(() => {
          import('./app.js').then(mod => mod.sendFromCard(opt.label));
        }, 300);
      });
      opts.appendChild(btn);
    });
    el.appendChild(opts);
  }

  if (cfg.steps && cfg.steps.length) {
    const stepsEl = document.createElement('div');
    stepsEl.className = 'plan-steps';
    cfg.steps.forEach((s, si) => {
      const step = document.createElement('div');
      step.className = 'plan-step';
      step.style.animationDelay = (delay + si * 80) + 'ms';
      step.innerHTML = `<span class="step-num">${String(si+1).padStart(2,'0')}</span><span class="step-text">${s}</span>`;
      stepsEl.appendChild(step);
    });
    el.appendChild(stepsEl);
  }

  if (cfg.flow && cfg.flow.length) {
    el.appendChild(buildFlowSVG(cfg.flow));
  }

  el.addEventListener('click', () => setActiveCard(index));
  cardsScroll.appendChild(el);
  cardElements.push(el);
  return el;
}

export function setActiveCard(idx) {
  if (!cardElements.length) return;
  idx = Math.max(0, Math.min(idx, cardElements.length - 1));
  activeCardIndex = idx;

  cardElements.forEach((el, i) => {
    el.classList.remove('active', 'inactive');
    if (i === idx) el.classList.add('active');
    else           el.classList.add('inactive');
  });

  updateScrollDots();

  const active = cardElements[idx];
  if (active) {
    active.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(() => fireBurst(active), 200);
  }
}

function updateScrollDots() {
  const dotsEl = document.getElementById('scroll-dots');
  if (!dotsEl) return;
  dotsEl.innerHTML = '';
  cardElements.forEach((_, i) => {
    const d = document.createElement('div');
    d.className = 'sdot' + (i === activeCardIndex ? ' active' : '');
    d.addEventListener('click', () => setActiveCard(i));
    dotsEl.appendChild(d);
  });
}

function buildFlowSVG(nodes) {
  const W = 290, H = nodes.length * 54 + 20;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('class', 'flowchart-svg');

  nodes.forEach((n, i) => {
    const y = i * 54 + 10;
    const cx = W / 2, cy = y + 18;

    if (i > 0) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', cx); line.setAttribute('y1', y - 6);
      line.setAttribute('x2', cx); line.setAttribute('y2', y + 2);
      line.setAttribute('stroke', 'rgba(0,245,255,0.3)');
      line.setAttribute('stroke-width', '1');
      line.setAttribute('stroke-dasharray', '3,3');
      svg.appendChild(line);
    }

    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', 20); rect.setAttribute('y', y);
    rect.setAttribute('width', W - 40); rect.setAttribute('height', 32);
    rect.setAttribute('rx', '3');
    rect.setAttribute('fill', 'rgba(0,245,255,0.05)');
    rect.setAttribute('stroke', 'rgba(0,245,255,0.25)');
    rect.setAttribute('stroke-width', '1');
    svg.appendChild(rect);

    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('x', cx); txt.setAttribute('y', cy + 5);
    txt.setAttribute('text-anchor', 'middle');
    txt.setAttribute('fill', 'rgba(168,184,208,0.9)');
    txt.setAttribute('font-size', '11');
    txt.setAttribute('font-family', 'Share Tech Mono,monospace');
    txt.textContent = n.label || n;
    svg.appendChild(txt);
  });

  const wrap = document.createElement('div');
  wrap.appendChild(svg);
  return wrap;
}
