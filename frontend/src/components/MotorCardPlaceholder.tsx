import { WifiOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '../utils/cn';

interface MotorCardPlaceholderProps {
  index: number;
  dense?: boolean;
  className?: string;
  footer?: ReactNode;
}

export function MotorCardPlaceholder({ index, dense = false, className, footer }: MotorCardPlaceholderProps) {
  const containerClasses = dense
    ? 'p-6 h-64'
    : 'p-8';

  return (
    <div
      className={cn(
        'relative bg-gray-800/50 rounded-3xl border-2 border-dashed border-gray-600 opacity-50',
        containerClasses,
        className
      )}
    >
      <div className="absolute inset-0 bg-gray-900/80 rounded-3xl flex items-center justify-center">
        <div className="text-center">
          <WifiOff className="w-8 h-8 text-gray-400 mx-auto mb-2" />
          <p className="text-sm font-semibold text-gray-400">Motor {index + 1}</p>
          <p className="text-xs text-gray-500">Disconnected</p>
        </div>
      </div>

      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 bg-gray-600 rounded-2xl flex items-center justify-center">
            <span className="text-gray-400 font-bold text-sm">{index + 1}</span>
          </div>
          <div>
            <h3 className="text-xl font-bold text-gray-500">Motor {index + 1}</h3>
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Joint Controller</p>
          </div>
        </div>
        <div className="w-4 h-4 rounded-full bg-gray-600" />
      </div>

      <div className="bg-gray-700 rounded-2xl p-4 mb-6">
        <p className="text-sm font-semibold text-gray-500 mb-1">Position</p>
        <div className="text-3xl font-black text-gray-500">--°</div>
      </div>

      <div className="space-y-3">
        <p className="text-sm font-semibold text-gray-500">Limit Switches</p>
        <div className="grid grid-cols-2 gap-3">
          {[ 'Top', 'Bottom' ].map((label) => (
            <div key={label} className="bg-gray-700 rounded-xl p-3">
              <div className="flex items-center space-x-3">
                <div className="w-5 h-5 rounded-full bg-gray-600" />
                <div>
                  <p className="text-sm font-semibold text-gray-500">{label}</p>
                  <p className="text-xs font-medium text-gray-500">--</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {footer}
    </div>
  );
}
