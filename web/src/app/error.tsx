'use client';

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-6" style={{ color: 'var(--j-text-dim)' }}>
      <div className="text-3xl mb-3" style={{ color: '#ff4757' }}>⚠</div>
      <h2 className="text-sm font-medium mb-1" style={{ color: 'var(--j-text)' }}>Something went wrong</h2>
      <p className="text-[11px] max-w-xs mb-4" style={{ color: 'var(--j-text-dim)' }}>
        {error.message || 'An unexpected error occurred'}
      </p>
      <button
        onClick={() => reset()}
        className="px-4 py-2 text-xs rounded-lg transition-all"
        style={{ background: 'var(--j-sky)', color: '#000' }}
      >
        Try again
      </button>
    </div>
  );
}
