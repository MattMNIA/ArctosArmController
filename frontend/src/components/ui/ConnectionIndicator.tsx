import { Wifi, WifiOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '../../utils/cn';

interface ConnectionIndicatorProps {
  connected: boolean;
  connectedLabel?: ReactNode;
  disconnectedLabel?: ReactNode;
  className?: string;
}

export function ConnectionIndicator({
  connected,
  connectedLabel = 'Connected',
  disconnectedLabel = 'Disconnected',
  className,
}: ConnectionIndicatorProps) {
  return (
    <div className={cn('flex items-center justify-center gap-2 text-sm font-semibold', className)}>
      {connected ? (
        <>
          <Wifi className="w-4 h-4 text-green-400" />
          <span className="text-green-400">{connectedLabel}</span>
        </>
      ) : (
        <>
          <WifiOff className="w-4 h-4 text-red-400" />
          <span className="text-red-400">{disconnectedLabel}</span>
        </>
      )}
    </div>
  );
}
