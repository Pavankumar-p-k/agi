import type { ReactNode } from 'react';

export function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="empty-state"><div className="empty-icon">○</div><strong>{title}</strong><p>{description}</p></div>;
}
export function PageFrame({ eyebrow, title, description, action, children }: { eyebrow: string; title: string; description: string; action?: ReactNode; children?: ReactNode }) {
  return <><div className="hero"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>{children}</>;
}
