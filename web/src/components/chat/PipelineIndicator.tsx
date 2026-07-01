'use client';

/* ── Chat Pipeline Indicator ──
 *
 * Shows the 7-stage JARVIS pipeline (Goal → Planner → Capability →
 * Provider → Permission → Execution → Learning) with animated stage
 * progression while a message is being processed.
 *
 * Educational/visual only — no backend dependency.
 * ─────────────────────────────────────────────────────── */

const PIPELINE = [
  { key: 'goal', label: 'Goal', icon: '🎯' },
  { key: 'planner', label: 'Planner', icon: '📋' },
  { key: 'capability', label: 'Capability', icon: '⚡' },
  { key: 'provider', label: 'Provider', icon: '🔌' },
  { key: 'permission', label: 'Permission', icon: '🛡️' },
  { key: 'execution', label: 'Execution', icon: '⚙️' },
  { key: 'learning', label: 'Learning', icon: '🧠' },
] as const;

interface Props {
  phase: 'waiting' | 'streaming';
}

export default function PipelineIndicator({ phase }: Props) {
  /* During waiting: animate through stages up to "execution".
     During streaming: show "execution" pulsing, rest dimmer. */
  const activeIndex = phase === 'waiting' ? 2 : 5;  // capability or execution

  return (
    <div
      className="w-full px-4 py-3"
      style={{
        border: '1px solid var(--j-border)',
        borderRadius: 'var(--j-radius-md)',
        background: 'var(--j-surface)',
      }}
    >
      {/* Stage dots */}
      <div className="flex items-center gap-0">
        {PIPELINE.map((stage, i) => {
          const isActive = i === activeIndex;
          const isPast = i < activeIndex;
          return (
            <div
              key={stage.key}
              className="flex-1 flex flex-col items-center gap-1 transition-all duration-500"
              style={{ opacity: isActive ? 1 : isPast ? 0.6 : 0.4 }}
            >
              {/* Icon */}
              <span
                className="transition-all duration-500"
                style={{
                  fontSize: isActive ? 16 : 12,
                  lineHeight: 1,
                  transform: isActive ? 'scale(1.1)' : 'scale(1)',
                }}
              >
                {stage.icon}
              </span>
              {/* Label */}
              <span
                className="text-[7px] font-mono uppercase tracking-[0.12em] transition-all duration-500"
                style={{
                  color: isActive ? 'var(--j-sky)' : 'var(--j-text-dim)',
                }}
              >
                {stage.label}
              </span>
              {/* Dot bar */}
              <div
                className="h-0.5 w-full rounded-full transition-all duration-700"
                style={{
                  background: isPast
                    ? 'var(--j-sky)'
                    : isActive
                      ? `linear-gradient(90deg, var(--j-sky) 50%, transparent 50%)`
                      : 'var(--j-border)',
                  backgroundSize: isActive ? '200% 100%' : undefined,
                  animation: isActive ? 'pipeline-pulse 1.2s ease-in-out infinite' : undefined,
                }}
              />
            </div>
          );
        })}
      </div>

      {/* Status text */}
      <div className="mt-2 text-center">
        <span
          className="text-[9px] font-mono uppercase tracking-[0.12em]"
          style={{ color: 'var(--j-text-muted)' }}
        >
          {phase === 'waiting'
            ? 'Routing to best provider…'
            : 'Executing — streaming response'}
        </span>
      </div>

      <style>{`
        @keyframes pipeline-pulse {
          0%, 100% { background-position: 0% 0; }
          50% { background-position: 100% 0; }
        }
      `}</style>
    </div>
  );
}
