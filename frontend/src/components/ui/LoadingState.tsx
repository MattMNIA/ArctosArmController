import type { ReactNode } from 'react';
import { cn } from '../../utils/cn';
import { Spinner } from './Spinner';

interface LoadingStateProps {
  message?: ReactNode;
  className?: string;
}

export function LoadingState({ message = 'Loading...', className }: LoadingStateProps) {
  return (
    <div className={cn('flex items-center justify-center gap-3 text-gray-300', className)}>
      <Spinner size="lg" />
      <span className="text-base">{message}</span>
    </div>
  );
}
