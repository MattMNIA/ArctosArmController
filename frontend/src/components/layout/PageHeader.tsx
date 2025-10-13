import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import { cn } from '../../utils/cn';

interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  statusSlot?: ReactNode;
  actions?: ReactNode;
  centered?: boolean;
  className?: string;
  animate?: boolean;
}

const animationProps = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.6 },
};

export function PageHeader({
  title,
  description,
  statusSlot,
  actions,
  centered = false,
  className,
  animate = true,
}: PageHeaderProps) {
  const Wrapper = animate ? motion.div : 'div';

  return (
    <Wrapper
      {...(animate ? animationProps : {})}
      className={cn('mb-12', centered ? 'text-center' : '', className)}
    >
      <h1 className={cn('text-3xl md:text-4xl font-bold mb-4 text-white', centered ? 'mx-auto' : '')}>
        {title}
      </h1>
      <div className={cn('h-1 w-20 bg-blue-500 rounded-full mb-6', centered ? 'mx-auto' : '')} />

      {statusSlot && (
        <div className={cn('mb-6', centered ? 'flex justify-center' : '')}>
          {statusSlot}
        </div>
      )}

      {description && (
        <p className={cn('text-lg text-gray-300 max-w-2xl', centered ? 'mx-auto' : '')}>
          {description}
        </p>
      )}

      {actions && (
        <div className={cn('mt-6', centered ? 'flex justify-center' : '')}>
          {actions}
        </div>
      )}
    </Wrapper>
  );
}
