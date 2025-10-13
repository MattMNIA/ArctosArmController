import { motion } from 'framer-motion';
import { Grip } from 'lucide-react';
import { AnimatedButton } from './ui/AnimatedButton';

interface GripperControlProps {
  gripperInput: string;
  setGripperInput: (value: string) => void;
  connected: boolean;
  onOpenGripper: () => void;
  onCloseGripper: () => void;
  onSetGripper: () => void;
}

export default function GripperControl({
  gripperInput,
  setGripperInput,
  connected,
  onOpenGripper,
  onCloseGripper,
  onSetGripper
}: GripperControlProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.6, delay: 0.4 }}
      className="bg-gray-800 rounded-3xl shadow-lg border border-gray-700/50 p-6 h-full"
    >
      <div className="space-y-6 h-full flex flex-col">
        {/* Quick Actions */}
        <div className="grid grid-cols-2 gap-4">
          <AnimatedButton
            onClick={onOpenGripper}
            disabled={!connected}
            size="lg"
            leftIcon={<Grip className="w-5 h-5" />}
          >
            Open
          </AnimatedButton>

          <AnimatedButton
            onClick={onCloseGripper}
            disabled={!connected}
            size="lg"
            leftIcon={<Grip className="w-5 h-5 rotate-90" />}
          >
            Close
          </AnimatedButton>
        </div>

        {/* Precise Control */}
        <div className="bg-gray-900/50 rounded-2xl p-6 border border-gray-700/50 flex-1 flex flex-col">
          <h3 className="text-lg font-semibold text-white mb-4">Precise Position</h3>
          <div className="flex items-center space-x-4 flex-1">
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              placeholder="0.50"
              value={gripperInput}
              onChange={(e) => setGripperInput(e.target.value)}
              className="flex-1 px-4 py-3 rounded-xl border border-gray-600 bg-gray-700 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
            />
            <AnimatedButton
              onClick={onSetGripper}
              disabled={!connected}
              size="md"
              className="px-6"
            >
              Set
            </AnimatedButton>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            Range: 0.0 (fully open) to 1.0 (fully closed)
          </p>
        </div>
      </div>
    </motion.div>
  );
}