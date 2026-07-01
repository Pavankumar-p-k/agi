'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { AnimatePresence } from 'framer-motion';
import { api, type SetupStatus } from '@/lib/api';
import WelcomeCard from '@/components/setup/WelcomeCard';
import SystemCheck from '@/components/setup/SystemCheck';
import CapabilityStatus from '@/components/setup/CapabilityStatus';
import DemoCard from '@/components/setup/DemoCard';
import FinishCard from '@/components/setup/FinishCard';

type Step = 'welcome' | 'system' | 'capabilities' | 'demo' | 'finish';

export default function WelcomePage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>('welcome');
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [installing, setInstalling] = useState<string | null>(null);

  useEffect(() => {
    api.setup.status()
      .then(s => {
        setStatus(s);
        if (s.phase === 'complete') {
          router.replace('/');
        }
      })
      .catch(() => {});
  }, [router]);

  const handleInstall = useCallback(async (component: string) => {
    setInstalling(component);
    try {
      await api.setup.install(component);
      const updated = await api.setup.status();
      setStatus(updated);
    } catch {
      // silently fail — user can retry
    } finally {
      setInstalling(null);
    }
  }, []);

  const handleComplete = useCallback(async () => {
    try {
      await api.setup.complete();
    } catch {
      // non-blocking
    }
    router.push('/');
  }, [router]);

  return (
    <div
      className="flex items-center justify-center min-h-screen px-4"
      style={{
        background: 'radial-gradient(ellipse at 50% -10%, rgba(0,210,255,0.06), transparent 50%)',
      }}
    >
      <div className="w-full max-w-md">
        <AnimatePresence mode="wait">
          {step === 'welcome' && (
            <WelcomeCard key="welcome" onContinue={() => setStep('system')} />
          )}

          {step === 'system' && status && (
            <SystemCheck
              key="system"
              status={status}
              onInstall={handleInstall}
              onContinue={() => setStep('capabilities')}
              installing={installing}
            />
          )}

          {step === 'capabilities' && (
            <CapabilityStatus
              key="capabilities"
              status={status!}
              onContinue={() => setStep('demo')}
            />
          )}

          {step === 'demo' && (
            <DemoCard
              key="demo"
              onComplete={() => setStep('finish')}
              onSkip={() => setStep('finish')}
            />
          )}

          {step === 'finish' && (
            <FinishCard key="finish" onOpen={handleComplete} />
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
