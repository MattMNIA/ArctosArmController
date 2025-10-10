import { motion } from 'framer-motion';
import type { ComponentPropsWithoutRef, ReactNode } from 'react';
import { cn } from '../../utils/cn';
import { Spinner } from './Spinner';

const whileHoverDefault = { scale: 1.02 };
const whileTapDefault = { scale: 0.98 };

type ButtonVariant = 'primary' | 'success' | 'danger' | 'ghost' | 'secondary';
type ButtonSize = 'sm' | 'md' | 'lg';

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    'bg-blue-500 hover:bg-blue-600 text-white shadow-lg hover:shadow-xl',
  success:
    'bg-green-500 hover:bg-green-600 text-white shadow-lg hover:shadow-xl',
  danger:
    'bg-red-600 hover:bg-red-700 text-white shadow-lg hover:shadow-xl border border-red-500',
  ghost:
    'bg-transparent border border-gray-600 text-gray-200 hover:bg-gray-700/60',
  secondary:
    'bg-gray-700 hover:bg-gray-600 text-white shadow-md hover:shadow-lg',
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'text-sm px-3 py-2 rounded-lg',
  md: 'text-sm px-4 py-2.5 rounded-xl',
  lg: 'text-base px-6 py-3 rounded-2xl',
};

type MotionButtonProps = ComponentPropsWithoutRef<typeof motion.button>;

export interface AnimatedButtonProps
  extends Omit<MotionButtonProps, 'className' | 'children'> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  loading?: boolean;
  className?: string;
  children?: ReactNode;
}

export function AnimatedButton({
  variant = 'primary',
  size = 'md',
  leftIcon,
  rightIcon,
  loading = false,
  disabled,
  className,
  children,
  whileHover = whileHoverDefault,
  whileTap = whileTapDefault,
  ...rest
}: AnimatedButtonProps) {
  const isDisabled = disabled || loading;

  return (
    <motion.button
      whileHover={isDisabled ? undefined : whileHover}
      whileTap={isDisabled ? undefined : whileTap}
      className={cn(
        'inline-flex items-center justify-center gap-2 font-semibold transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed',
        variantClasses[variant],
        sizeClasses[size],
        className
      )}
      disabled={isDisabled}
      {...rest}
    >
      {loading ? (
        <Spinner size="sm" />
      ) : (
        <>
          {leftIcon}
          <span>{children}</span>
          {rightIcon}
        </>
      )}
    </motion.button>
  );
}
