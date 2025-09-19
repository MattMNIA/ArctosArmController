import { motion } from 'framer-motion';
import { Grip } from 'lucide-react';

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
          <motion.button
            onClick={onOpenGripper}
            disabled={!connected}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="flex items-center justify-center space-x-2 px-6 py-4 bg-blue-500 hover:bg-blue-600 text-white rounded-2xl font-semibold shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
          >
            <Grip className="w-5 h-5" />
            <span>Open</span>
          </motion.button>

          <motion.button
            onClick={onCloseGripper}
            disabled={!connected}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="flex items-center justify-center space-x-2 px-6 py-4 bg-blue-500 hover:bg-blue-600 text-white rounded-2xl font-semibold shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
          >
            <Grip className="w-5 h-5 rotate-90" />
            <span>Close</span>
          </motion.button>
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
            <motion.button
              onClick={onSetGripper}
              disabled={!connected}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="px-6 py-3 bg-blue-500 hover:bg-blue-600 text-white rounded-xl font-semibold shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
            >
              Set
            </motion.button>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            Range: 0.0 (fully open) to 1.0 (fully closed)
          </p>
        </div>
      </div>
    </motion.div>
  );
}