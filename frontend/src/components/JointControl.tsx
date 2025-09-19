import { motion } from 'framer-motion';
import { Play, Calculator } from 'lucide-react';

interface JointControlProps {
  jointInputs: string[];
  setJointInputs: (inputs: string[]) => void;
  connected: boolean;
  loading: boolean;
  onSolveIK: () => void;
  onExecuteMove: () => void;
}

export default function JointControl({
  jointInputs,
  setJointInputs,
  connected,
  loading,
  onSolveIK,
  onExecuteMove
}: JointControlProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.6, delay: 0.2 }}
      className="bg-gray-800 rounded-3xl shadow-lg border border-gray-700/50 p-6 h-full"
    >
      <div className="space-y-4 h-full flex flex-col">
        {jointInputs.map((input, index) => (
          <motion.div
            key={index}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
            className="flex items-center space-x-4"
          >
            <label className="text-sm font-semibold text-gray-300 w-20">
              Joint {index + 1}
            </label>
            <input
              type="number"
              step="0.01"
              min="-180"
              max="180"
              placeholder="0.00"
              value={input}
              onChange={(e) => {
                const newInputs = [...jointInputs];
                newInputs[index] = e.target.value;
                setJointInputs(newInputs);
              }}
              className="flex-1 px-4 py-3 rounded-xl border border-gray-600 bg-gray-700 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
            />
            <span className="text-sm text-gray-400 w-8">°</span>
          </motion.div>
        ))}

        <div className="flex gap-4 mt-auto">
          <motion.button
            onClick={onSolveIK}
            disabled={loading || !connected}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="flex-1 flex items-center justify-center space-x-2 px-6 py-3 bg-blue-500 hover:bg-blue-600 text-white rounded-xl font-semibold shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
          >
            <Calculator className="w-5 h-5" />
            <span>{loading ? 'Solving...' : 'Solve IK'}</span>
          </motion.button>

          <motion.button
            onClick={onExecuteMove}
            disabled={loading || !connected}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="flex-1 flex items-center justify-center space-x-2 px-6 py-3 bg-green-500 hover:bg-green-600 text-white rounded-xl font-semibold shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
          >
            <Play className="w-5 h-5" />
            <span>{loading ? 'Executing...' : 'Execute'}</span>
          </motion.button>
        </div>
      </div>
    </motion.div>
  );
}