'use client';

import { useEffect, useMemo, useState, useRef } from 'react';
import { motion } from 'framer-motion';
import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import { WSClient } from '@/lib/ws';

const MASCOT_FRAMES = [
`    .-^-.    
  .<>   <>.  
 <>  JAR  <>
  '<>   <>'
    '-v-'    `,
`    .-^-.    
  .<>   <>.  
 <>  VIS  <>
  '<>   <>'
    '-v-'    `,
`    .-*-.    
  .<<   >>.  
 <>  CLI  <>
  '>>   <<'
    '-*-'    `,
`    .-^-.    
  .<>   <>.  
 <>  OS   <>
  '<>   <>'
    '-v-'    `,
];

const AGENTS = [
  { name: 'MAESTRO', role: 'Routes every task to the right agent', kind: 'orchestrator', color: '#bc8cff', prompt: 'How does the MAESTRO orchestrator route tasks between Jarvis agents in the CLI?' },
  { name: 'NEXUS', role: 'Deep research, synthesis, intel briefs', kind: 'research', color: '#58a6ff', prompt: 'How does NEXUS deep research work in Jarvis CLI?' },
  { name: 'FORGE', role: 'Code gen, debug, refactor, docs', kind: 'code', color: '#e3b341', prompt: 'How does FORGE code generation work in Jarvis CLI?' },
  { name: 'ORACLE', role: 'Goal plans, task decomposition', kind: 'planning', color: '#3fb950', prompt: 'How does ORACLE goal planning work in Jarvis CLI?' },
  { name: 'CIPHER', role: 'Security audit, threat model', kind: 'security', color: '#f85149', prompt: 'How does CIPHER security auditing work in Jarvis CLI?' },
  { name: 'HERALD', role: 'Draft messages, summarize, reply', kind: 'comms', color: '#39d0d8', prompt: 'How does HERALD message drafting work in Jarvis CLI?' },
  { name: 'ATLAS', role: 'SQL, pandas, visualization', kind: 'data', color: '#d2a8ff', prompt: 'How does ATLAS data analysis work in Jarvis CLI?' },
  { name: 'SCRIBE', role: 'Docs, READMEs, changelogs', kind: 'docs', color: '#adbac7', prompt: 'How does SCRIBE technical documentation work in Jarvis CLI?' },
  { name: 'SENTINEL', role: 'Health, diagnostics, live metrics', kind: 'monitor', color: '#3fb950', prompt: 'How does SENTINEL system health monitoring work in Jarvis CLI?' },
];

const CLI_FEATURES = [
  { title: 'Natural language routing', command: 'python jarvis.py "find security issues in auth.py"', desc: 'MAESTRO infers intent, previews routing, then hands work to the right specialist.' },
  { title: 'Interactive REPL', command: 'python jarvis.py cli', desc: 'prompt_toolkit shell with history, autocomplete, slash commands, sessions, and streaming replies.' },
  { title: 'Agent shortcuts', command: 'python jarvis.py forge "refactor cli_commands.py"', desc: 'Every specialist is directly callable from the terminal for fast expert-mode tasks.' },
  { title: 'Backend + web launcher', command: 'python jarvis.py web --host 127.0.0.1 --port 8000', desc: 'Builds the web UI, starts the FastAPI stack, and opens the browser control plane.' },
  { title: 'Plugin operations', command: 'python jarvis.py plugin list', desc: 'Install, enable, disable, and inspect plugins without leaving the CLI workflow.' },
  { title: 'Diagnostics', command: 'python jarvis.py doctor --json', desc: 'Dependency, server, model, and degraded-response checks for local repair loops.' },
];

function queuePrompt(prompt: string) {
  localStorage.setItem('jarvis:queuedPrompt', prompt);
  window.location.href = '/chat';
}

function copyCommand(command: string) {
  navigator.clipboard.writeText(command);
}

export default function CliPage() {
  const [frame, setFrame] = useState(0);
  const [lines, setLines] = useState<{ text: string; color?: string; type?: string }[]>([]);
  const [command, setCommand] = useState('');
  const wsRef = useRef<WSClient | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const frameTimer = setInterval(() => setFrame(v => (v + 1) % MASCOT_FRAMES.length), 360);
    
    const ws = new WSClient('/ws/terminal');
    wsRef.current = ws;
    ws.connect();

    ws.on('_connected', () => {
      setLines(prev => [...prev, { text: 'CONNECTED TO JARVIS TERMINAL', color: '#28c840' }]);
    });
    ws.on('_disconnected', () => {
      setLines(prev => [...prev, { text: 'CONNECTION LOST. RECONNECTING...', color: '#ff4757' }]);
    });
    ws.on('output', (data: any) => {
      setLines(prev => [...prev, { 
        text: data.data, 
        color: data.stream === 'stderr' ? '#ff4757' : 'var(--j-text)',
        type: 'output'
      }]);
    });

    return () => {
      clearInterval(frameTimer);
      ws.disconnect();
    };
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines]);

  const handleCommand = (e: React.FormEvent) => {
    e.preventDefault();
    if (!command.trim() || !wsRef.current) return;
    setLines(prev => [...prev, { text: `> ${command}`, color: 'var(--j-sky)' }]);
    wsRef.current.send({ type: 'command', data: command });
    setCommand('');
  };

  return (
    <div className="hud-page h-full overflow-y-auto space-y-7">
      <section className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="relative z-[1] grid grid-cols-1 gap-8 xl:grid-cols-[0.95fr_1.05fr] xl:items-center">
          <div>
            <div className="hud-label">Terminal Control Plane</div>
            <h1 className="hud-title mt-3 text-7xl md:text-8xl">CLI <span className="text-[var(--j-sky)]">Mode</span></h1>
            <p className="mt-5 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
              Direct WebSocket link to the JARVIS backend shell. Execute system commands,
              manage agents, and trigger automation pipelines from the browser.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button variant="primary" onClick={() => queuePrompt('Show me common JARVIS CLI commands.')}>Common Commands</Button>
              <Button variant="ghost" onClick={() => copyCommand('python jarvis.py cli')}>Copy Local Command</Button>
            </div>
          </div>

          <div className="overflow-hidden border border-[#30363d] bg-[#0d1117] flex flex-col h-[400px]">
            <div className="flex items-center gap-2 border-b border-[#30363d] bg-[#161b22] px-4 py-3 shrink-0">
              <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
              <span className="ml-2 font-mono text-[11px] text-[#8b949e]">jarvis-shell</span>
            </div>
            <div 
              ref={scrollRef}
              className="flex-1 p-5 overflow-y-auto font-mono text-xs leading-6 scrollbar-hide"
            >
              <div className="grid grid-cols-1 gap-6 md:grid-cols-[180px_1fr] mb-4">
                <pre className="whitespace-pre font-mono text-[10px] leading-[1.3] text-[#58a6ff]">{MASCOT_FRAMES[frame]}</pre>
                <div className="text-[var(--j-sky)] uppercase tracking-widest text-[9px] flex items-end pb-1">
                  Ready for Input
                </div>
              </div>
              {lines.map((line, i) => (
                <div key={i} style={{ color: line.color }} className={line.type === 'output' ? 'whitespace-pre-wrap' : ''}>
                  {line.text}
                </div>
              ))}
              <div className="flex gap-2 mt-2">
                <span className="text-[var(--j-sky)] shrink-0">jarvis@core:~$</span>
                <form onSubmit={handleCommand} className="flex-1">
                  <input
                    autoFocus
                    value={command}
                    onChange={(e) => setCommand(e.target.value)}
                    className="w-full bg-transparent border-none outline-none text-[var(--j-text)] p-0 m-0"
                  />
                </form>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-center justify-between gap-4">
          <div>
            <div className="hud-label">9 Agents</div>
            <h2 className="hud-title mt-2 text-5xl">Live In <span className="text-[var(--j-sky)]">Terminal</span></h2>
          </div>
          <Badge variant="new">Registered in jarvis.py</Badge>
        </div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] sm:grid-cols-2 xl:grid-cols-3">
          {AGENTS.map(agent => (
            <button
              key={agent.name}
              onClick={() => queuePrompt(agent.prompt)}
              className="group bg-[var(--j-surface)] p-5 text-left transition-all hover:bg-[var(--j-surface-hover)]"
            >
              <span className="mb-4 inline-block border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: agent.color, borderColor: agent.color, background: 'rgba(0,0,0,0.18)' }}>{agent.kind}</span>
              <div className="font-display text-4xl tracking-[0.1em]" style={{ color: agent.color }}>{agent.name}</div>
              <p className="mt-2 text-sm leading-6 text-[var(--j-text-dim)]">{agent.role}</p>
              <div className="mt-4 font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--j-text-muted)] group-hover:text-[var(--j-sky)]">
                ask how it works
              </div>
            </button>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-4">
          <div className="hud-label">CLI Features Mapped To Code</div>
          <h2 className="hud-title mt-2 text-5xl">Command <span className="text-[var(--j-sky)]">Links</span></h2>
        </div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] lg:grid-cols-2">
          {CLI_FEATURES.map(feature => (
            <div key={feature.title} className="bg-[var(--j-surface)] p-5">
              <div className="font-display text-3xl tracking-[0.08em]">{feature.title}</div>
              <button
                onClick={() => copyCommand(feature.command)}
                className="mt-3 block w-full border border-[var(--j-border)] bg-[#020a0f] px-3 py-3 text-left font-mono text-[11px] text-[var(--j-sky)] transition-all hover:border-[var(--j-border-bright)]"
              >
                {feature.command}
              </button>
              <p className="mt-3 text-sm leading-6 text-[var(--j-text-dim)]">{feature.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="grid grid-cols-1 gap-px bg-[var(--j-border)] lg:grid-cols-2">
        <div className="bg-[var(--j-surface)] p-6">
          <div className="hud-label">Jarvis Has</div>
          {['9 specialized sub-agents', 'Interactive prompt_toolkit CLI', 'Slash commands + sessions', 'Plugin and skills control', 'Backend/web launch command', 'Docker sandbox and SSRF policy'].map(item => (
            <div key={item} className="border-b border-[var(--j-border)] py-2 font-mono text-xs text-[var(--j-text)]"><span className="text-[#28c840]">+</span> {item}</div>
          ))}
        </div>
      </section>

      <section className="hud-panel p-5">
        <div className="hud-label mb-4">Prompt Links</div>
        <div className="flex flex-wrap gap-2">
          {[
            ['Diamond frames', 'Write all ASCII diamond mascot animation frames for Jarvis CLI in Python for prompt_toolkit.'],
            ['Boot code', 'Write the Jarvis CLI boot sequence in Python with ASCII diamond animation and agent system check lines.'],
            ['Routing display', 'Build the MAESTRO agent routing display for Jarvis CLI with animated spinner.'],
            ['Agent spinners', 'Design per-agent ASCII spinners for all 9 Jarvis agents.'],
          ].map(([label, prompt]) => (
            <Button key={label} variant="ghost" size="sm" onClick={() => queuePrompt(prompt)}>{label}</Button>
          ))}
        </div>
      </section>
    </div>
  );
}
