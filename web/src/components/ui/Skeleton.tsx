'use client';

import { motion } from 'framer-motion';

export function SkeletonBar({ className = '' }: { className?: string }) {
  return (
    <motion.div
      animate={{ opacity: [0.3, 0.6, 0.3] }}
      transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
      className={`${className}`}
      style={{ background: 'linear-gradient(90deg, rgba(var(--j-sky-rgb),0.07), rgba(var(--j-sky-rgb),0.18), rgba(var(--j-sky-rgb),0.07))' }}
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="hud-panel p-4">
      <SkeletonBar className="h-3 w-16 mb-3" />
      <SkeletonBar className="h-24 w-full mb-3" />
      <SkeletonBar className="h-3 w-24" />
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-5">
      <SkeletonBar className="h-32 w-full" />
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <SkeletonCard /><SkeletonCard /><SkeletonCard />
      </div>
    </div>
  );
}

export function MonitorSkeleton() {
  return (
    <div className="space-y-4">
      <SkeletonBar className="h-5 w-24" />
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SkeletonCard /><SkeletonCard /><SkeletonCard />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SkeletonCard /><SkeletonCard /><SkeletonCard />
      </div>
    </div>
  );
}
