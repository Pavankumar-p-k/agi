import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';
import { createElement } from 'react';

vi.mock('@jarvis/ui', () => ({
  StatusDot: (props: any) => createElement('span', { 'data-testid': 'status-dot', ...props }),
  ProgressBar: (props: any) => createElement('div', { 'data-testid': 'progress-bar', 'data-value': props.value },
    props.label ? createElement('span', null, props.label) : null,
  ),
  EmptyState: (props: any) => createElement('div', { 'data-testid': 'empty-state' },
    createElement('h3', null, props.title),
    createElement('p', null, props.description),
  ),
}));
