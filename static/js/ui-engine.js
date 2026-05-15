'use strict';

const registry = {};
let currentContainer = null;
let currentBlueprint = null;

export function registerComponent(type, renderFn) {
  registry[type] = renderFn;
}

export function renderBlueprint(blueprint) {
  if (!blueprint || !blueprint.components) return;

  currentBlueprint = blueprint;
  cleanupContainer();

  const container = document.createElement('div');
  container.className = 'bp-container';

  if (blueprint.layout) {
    if (blueprint.layout.columns) {
      container.style.setProperty('--bp-columns', blueprint.layout.columns);
      container.style.setProperty('--bp-gap', (blueprint.layout.gap || 16) + 'px');
    }
    if (blueprint.layout.background === 'dark') {
      container.style.background = 'rgba(4,4,13,0.6)';
    }
  }

  const anim = blueprint.animations || {};
  container.dataset.enter = anim.enter || 'fade_up';
  container.dataset.exit = anim.exit || 'fade_out';

  blueprint.components.forEach((comp, i) => {
    const renderFn = registry[comp.type];
    if (renderFn) {
      const el = renderFn(comp.data, i);
      if (el) {
        el.style.animationDelay = (i * 80) + 'ms';
        el.classList.add('bp-comp');
        container.appendChild(el);
      }
    }
  });

  const target = document.getElementById('cards-scroll');
  if (target) {
    target.appendChild(container);
    currentContainer = container;
  }

  return container;
}

export function clearBlueprint() {
  cleanupContainer();
  currentBlueprint = null;
}

function cleanupContainer() {
  if (currentContainer && currentContainer.parentNode) {
    currentContainer.parentNode.removeChild(currentContainer);
    currentContainer = null;
  }
  const existing = document.querySelector('.bp-container');
  if (existing) existing.remove();
}

// ════════════════════════════════════════════════════════════
//  BUILT-IN COMPONENT RENDERERS
// ════════════════════════════════════════════════════════════

// ── Heading ──
registerComponent('heading', (data) => {
  const el = document.createElement('div');
  el.className = 'bp-heading';
  el.textContent = data.text || '';
  if (data.level === 1) el.style.fontSize = '20px';
  else if (data.level === 2) el.style.fontSize = '16px';
  else el.style.fontSize = '14px';
  return el;
});

// ── Card ──
registerComponent('card', (data) => {
  const el = document.createElement('div');
  el.className = 'bp-card';
  if (data.icon) el.innerHTML = `<span class="bp-card-icon">${data.icon}</span>`;
  if (data.title) el.innerHTML += `<div class="bp-card-title">${data.title}</div>`;
  if (data.text) el.innerHTML += `<div class="bp-card-text">${data.text}</div>`;
  return el;
});

// ── Chart (SVG bar chart) ──
registerComponent('chart', (data) => {
  const type = data.type || 'bar';
  const labels = data.labels || [];
  const values = data.values || [];
  if (values.length === 0) return null;

  const W = 280, H = 160, PAD = 30;
  const maxVal = Math.max(...values) || 1;
  const barW = (W - PAD * 2) / values.length;

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('class', 'bp-chart');

  // Grid lines
  for (let i = 0; i <= 4; i++) {
    const y = PAD + (H - PAD * 2) * (1 - i / 4);
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', PAD); line.setAttribute('y1', y);
    line.setAttribute('x2', W - 5); line.setAttribute('y2', y);
    line.setAttribute('stroke', 'rgba(0,245,255,0.08)');
    line.setAttribute('stroke-width', '1');
    svg.appendChild(line);
  }

  // Bars
  values.forEach((v, i) => {
    const barH = (v / maxVal) * (H - PAD * 2);
    const x = PAD + i * barW + barW * 0.1;
    const y = H - PAD - barH;
    const bw = barW * 0.8;

    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', x); rect.setAttribute('y', y);
    rect.setAttribute('width', bw); rect.setAttribute('height', barH);
    rect.setAttribute('rx', '2');
    rect.setAttribute('fill', type === 'bar' ? 'rgba(0,245,255,0.7)' : 'rgba(0,255,157,0.7)');
    svg.appendChild(rect);

    if (labels[i]) {
      const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      txt.setAttribute('x', x + bw / 2); txt.setAttribute('y', H - 5);
      txt.setAttribute('text-anchor', 'middle');
      txt.setAttribute('fill', 'rgba(168,184,208,0.6)');
      txt.setAttribute('font-size', '8');
      txt.setAttribute('font-family', 'Share Tech Mono,monospace');
      txt.textContent = labels[i].slice(0, 6);
      svg.appendChild(txt);
    }
  });

  const wrap = document.createElement('div');
  wrap.appendChild(svg);
  return wrap;
});

// ── Timeline ──
registerComponent('timeline', (data) => {
  const steps = data.steps || data || [];
  if (!steps.length) return null;

  const el = document.createElement('div');
  el.className = 'bp-timeline';

  steps.forEach((s, i) => {
    const step = document.createElement('div');
    step.className = 'bp-tl-step';
    step.innerHTML = `
      <div class="bp-tl-dot"></div>
      <div class="bp-tl-content">
        <div class="bp-tl-title">${s.title || s.label || s}</div>
        ${s.desc ? `<div class="bp-tl-desc">${s.desc}</div>` : ''}
      </div>
    `;
    el.appendChild(step);
  });

  return el;
});

// ── Action Buttons ──
registerComponent('action_buttons', (data) => {
  const options = data.options || data.buttons || [];
  if (!options.length) return null;

  const el = document.createElement('div');
  el.className = 'bp-actions';

  options.forEach(opt => {
    const btn = document.createElement('button');
    btn.className = 'bp-action-btn';
    btn.innerHTML = `${opt.icon || '▸'} ${opt.label || opt}`;
    if (opt.action) {
      btn.addEventListener('click', () => {
        import('./app.js').then(mod => mod.sendFromCard(opt.action));
      });
    }
    el.appendChild(btn);
  });

  return el;
});

// ── Stats Grid ──
registerComponent('stats', (data) => {
  const items = data.items || [];
  if (!items.length) return null;

  const el = document.createElement('div');
  el.className = 'bp-stats';

  items.forEach(item => {
    const stat = document.createElement('div');
    stat.className = 'bp-stat';
    stat.innerHTML = `
      <div class="bp-stat-value">${item.value || 0}</div>
      <div class="bp-stat-label">${item.label || ''}</div>
    `;
    el.appendChild(stat);
  });

  return el;
});

// ── Table ──
registerComponent('table', (data) => {
  const headers = data.headers || [];
  const rows = data.rows || [];
  if (!headers.length) return null;

  const el = document.createElement('div');
  el.className = 'bp-table-wrap';

  let html = '<table class="bp-table"><thead><tr>';
  headers.forEach(h => { html += `<th>${h}</th>`; });
  html += '</tr></thead><tbody>';
  rows.forEach(row => {
    html += '<tr>';
    headers.forEach((h, i) => { html += `<td>${row[h] || row[i] || ''}</td>`; });
    html += '</tr>';
  });
  html += '</tbody></table>';
  el.innerHTML = html;
  return el;
});

// ── Flowchart ──
registerComponent('flowchart', (data) => {
  const nodes = data.nodes || data.steps || [];
  if (!nodes.length) return null;

  const W = 280, H = nodes.length * 54 + 20;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('class', 'bp-flowchart');

  nodes.forEach((n, i) => {
    const y = i * 54 + 10, cx = W / 2, cy = y + 18;

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
});
