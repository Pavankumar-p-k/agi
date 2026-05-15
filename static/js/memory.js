'use strict';

import { addNode } from './graph.js';

export async function fetchAndSeedNodes() {
  try {
    const res = await fetch('http://localhost:8000/api/chat/history');
    if (!res.ok) {
      seedSampleNodes();
      return;
    }
    const data = await res.json();

    if (Array.isArray(data) && data.length > 0) {
      data.forEach(entry => {
        addNode({
          type: 'memory',
          label: entry.role || 'assistant',
          text: entry.message || entry.content || '',
          timestamp: entry.ts || null,
          source: 'conversation',
        });
      });
    } else {
      seedSampleNodes();
    }
  } catch (_) {
    seedSampleNodes();
  }
}

function seedSampleNodes() {
  const samples = [
    { type: 'memory', label: 'system', text: 'JARVIS Neural OS initialized. All systems operational.', source: 'system' },
    { type: 'memory', label: 'concept', text: 'Particle node graph: each node represents a discrete knowledge cell.', source: 'system' },
  ];
  samples.forEach(s => addNode(s));
}
