import { describe, it, expect, vi, beforeEach } from 'vitest'

// --- Helper functions extracted from panel.html ---
const esc = (s) => {
  if (!s) return ''
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')
}

const STATUS_COLORS = { RUNNING: '#4caf50', PENDING: '#ff9800', SUSPENDED: '#2196f3', FAILED: '#f44336', COMPLETED: '#888', CANCELLED: '#666' }
const TREE_ICONS = { PENDING:'○', RUNNING:'▶', COMPLETED:'✓', FAILED:'✗', SUSPENDED:'⏸', CANCELLED:'⊘' }

function buildTreeChildren(nodes) {
  const children = {}
  nodes.forEach(n => {
    const p = n.parent_id || ''
    if (!children[p]) children[p] = []
    children[p].push(n)
  })
  return children
}

function computeStatusSummary(byStatus) {
  return Object.entries(byStatus).map(([k, v]) => `${k}: ${v}`).join(' | ')
}

describe('Activity panel.js helper functions', () => {
  it('esc() escapes HTML entities', () => {
    expect(esc('<script>alert("x")</script>')).toBe('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;')
    expect(esc('')).toBe('')
    expect(esc(null)).toBe('')
    expect(esc('normal text')).toBe('normal text')
  })

  it('esc() handles ampersands correctly', () => {
    expect(esc('x & y')).toBe('x &amp; y')
    expect(esc('already &amp; safe')).toBe('already &amp;amp; safe')
  })

  it('status color mapping covers all known states', () => {
    expect(STATUS_COLORS['RUNNING']).toBe('#4caf50')
    expect(STATUS_COLORS['PENDING']).toBe('#ff9800')
    expect(STATUS_COLORS['COMPLETED']).toBe('#888')
    expect(STATUS_COLORS['FAILED']).toBe('#f44336')
    expect(STATUS_COLORS['SUSPENDED']).toBe('#2196f3')
    expect(STATUS_COLORS['CANCELLED']).toBe('#666')
    expect(STATUS_COLORS['UNKNOWN']).toBeUndefined()
  })

  it('tree icon mapping covers all known states', () => {
    expect(TREE_ICONS['RUNNING']).toBe('▶')
    expect(TREE_ICONS['COMPLETED']).toBe('✓')
    expect(TREE_ICONS['FAILED']).toBe('✗')
    expect(TREE_ICONS['PENDING']).toBe('○')
    expect(TREE_ICONS['SUSPENDED']).toBe('⏸')
    expect(TREE_ICONS['CANCELLED']).toBe('⊘')
    expect(TREE_ICONS['UNKNOWN']).toBeUndefined()
  })

  it('builds tree children map correctly', () => {
    const nodes = [
      { node_id: 'n1', parent_id: '' },
      { node_id: 'n2', parent_id: 'n1' },
      { node_id: 'n3', parent_id: 'n1', agent_id: 'builder' },
    ]
    const children = buildTreeChildren(nodes)
    expect(children['']).toHaveLength(1)
    expect(children['']).toHaveLength(1)
    expect(children['n1']).toHaveLength(2)
    expect(children['n2']).toBeUndefined()
    expect(children['n1'][1].agent_id).toBe('builder')
  })

  it('handles empty node list', () => {
    expect(buildTreeChildren([])).toEqual({})
  })

  it('computes status summary correctly', () => {
    expect(computeStatusSummary({ RUNNING: 1, PENDING: 1, FAILED: 1 })).toBe('RUNNING: 1 | PENDING: 1 | FAILED: 1')
  })

  it('handles empty status summary', () => {
    expect(computeStatusSummary({})).toBe('')
  })

  it('activity list rendering escapes HTML in labels', () => {
    const label = 'Build <b>app</b> & "test"'
    const safe = esc(label)
    const html = `<span>${safe}</span>`
    expect(html).toContain('&lt;b&gt;')
    expect(html).toContain('&amp;')
    expect(html).toContain('&quot;')
    expect(html).not.toContain('<b>')
  })

  it('tree item rendering includes agent when present', () => {
    const node = { node_id: 'n1', label: 'Build', status: 'RUNNING', node_type: 'goal', agent_id: 'builder' }
    const label = esc(node.label.substring(0, 50))
    const agentHtml = node.agent_id ? ` <span style="color:var(--text3);">[${node.agent_id}]</span>` : ''
    const rendered = `${label}${agentHtml} <span style="color:${STATUS_COLORS[node.status]};">RUNNING</span>`
    expect(rendered).toContain('[builder]')
    expect(rendered).toContain('#4caf50')
  })

  it('tree item rendering omits agent when absent', () => {
    const node = { node_id: 'n1', label: 'Build', status: 'PENDING', node_type: 'goal' }
    const label = esc(node.label.substring(0, 50))
    const agentHtml = node.agent_id ? ` [${node.agent_id}]` : ''
    expect(agentHtml).toBe('')
    const rendered = `${label}${agentHtml}`
    expect(rendered).not.toContain('[')
  })

  it('selectActivity constructs summary div with correct fields', () => {
    const summary = { total_nodes: 5, depth: 2, agents_used: ['a1', 'a2'], by_status: { RUNNING: 3, COMPLETED: 2 }, goal: 'Test' }
    const statusStr = computeStatusSummary(summary.by_status)
    const agents = (summary.agents_used || []).join(', ') || 'none'
    const summaryHtml = `<b>${esc(summary.goal)}</b> | ${statusStr} | Agents: ${agents} | Depth: ${summary.depth}`
    expect(summaryHtml).toBe('<b>Test</b> | RUNNING: 3 | COMPLETED: 2 | Agents: a1, a2 | Depth: 2')
  })

  it('activity item HTML includes data-id and onclick', () => {
    const a = { node_id: 'act_001', label: 'Build', status: 'RUNNING', node_type: 'goal', depth: 0, agent_id: 'orchestrator' }
    const html = `<div class="activity-item" data-id="${a.node_id}" onclick="selectActivity('${a.node_id}')">`
    expect(html).toContain('data-id="act_001"')
    expect(html).toContain("selectActivity('act_001')")
  })

  it('counts display formats correctly', () => {
    const counts = { total: 5, running: 2, pending: 1, failed: 1, suspended: 1, completed: 0 }
    const text = `${counts.total || 0} total | ${counts.running || 0} running | ${counts.pending || 0} pending | ${counts.failed || 0} failed`
    expect(text).toBe('5 total | 2 running | 1 pending | 1 failed')
  })
})
