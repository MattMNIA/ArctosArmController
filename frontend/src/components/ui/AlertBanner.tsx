import { AlertTriangle, CheckCircle2, Info, AlertCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '../../utils/cn';
import { AnimatedButton } from './AnimatedButton';

const variantStyles = {
  error: {
    container: 'bg-red-900/20 border border-red-800 text-red-200',
    title: 'text-red-200',
    icon: <AlertCircle className="w-5 h-5 text-red-400" />,
    buttonVariant: 'danger' as const,
  },
  warning: {
    container: 'bg-yellow-900/20 border border-yellow-700 text-yellow-100',
    title: 'text-yellow-100',
    icon: <AlertTriangle className="w-5 h-5 text-yellow-400" />,
    buttonVariant: 'secondary' as const,
  },
  info: {
    container: 'bg-blue-900/20 border border-blue-800 text-blue-100',
    title: 'text-blue-100',
    icon: <Info className="w-5 h-5 text-blue-400" />,
    buttonVariant: 'secondary' as const,
  },
  success: {
    container: 'bg-green-900/20 border border-green-800 text-green-100',
    title: 'text-green-100',
    icon: <CheckCircle2 className="w-5 h-5 text-green-400" />,
    buttonVariant: 'success' as const,
  },
};

type Variant = keyof typeof variantStyles;

interface AlertAction {
  label: string;
  onClick: () => void;
  icon?: ReactNode;
  loading?: boolean;
  disabled?: boolean;
}

interface AlertBannerProps {
  title: string;
  message?: ReactNode;
  variant?: Variant;
  action?: AlertAction;
  className?: string;
}

export function AlertBanner({
  title,
  message,
  variant = 'info',
  action,
  className,
}: AlertBannerProps) {
  const styles = variantStyles[variant];

  return (
    <div className={cn('rounded-2xl px-5 py-4 flex items-center justify-between gap-4', styles.container, className)}>
      <div className="flex items-start gap-3">
        <div className="mt-0.5">
          {styles.icon}
        </div>
        <div>
          <h3 className={cn('font-semibold text-sm md:text-base', styles.title)}>{title}</h3>
          {message && (
            <div className="text-xs md:text-sm mt-1 opacity-90">
              {message}
            </div>
          )}
        </div>
      </div>

      {action && (
        <AnimatedButton
          variant={styles.buttonVariant}
          size="sm"
          onClick={action.onClick}
          loading={action.loading}
          disabled={action.disabled}
          leftIcon={action.icon}
          className="whitespace-nowrap"
        >
          {action.label}
        </AnimatedButton>
      )}
    </div>
  );
}
