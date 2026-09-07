'use client';

interface Props {
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

export function EmptyState({ title, description, action }: Props) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 24px',
        gap: 12,
        color: 'var(--j-text-dim)',
      }}
    >
      <span style={{ fontSize: 24, opacity: 0.4 }}>○</span>
      <span style={{ fontWeight: 500 }}>{title}</span>
      {description && <span style={{ fontSize: 13, textAlign: 'center', maxWidth: 300 }}>{description}</span>}
      {action && (
        <button
          onClick={action.onClick}
          style={{
            marginTop: 8,
            padding: '8px 20px',
            borderRadius: 4,
            border: '1px solid var(--j-border)',
            background: 'var(--j-surface)',
            color: 'var(--j-text)',
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
