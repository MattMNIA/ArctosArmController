import { motion } from 'framer-motion';
import { Play, Target } from 'lucide-react';
import { AnimatedButton } from './ui/AnimatedButton';

interface JointControlProps {
  jointInputs: string[];
  setJointInputs: (inputs: string[]) => void;
  connected: boolean;
  loading: boolean;
  onCalculateFK: () => void;
  onExecuteMove: () => void;
  fkResult: { position: number[]; orientation: number[] } | null;
}

export default function JointControl({
  jointInputs,
  setJointInputs,
  connected,
  loading,
  onCalculateFK,
  onExecuteMove,
  fkResult
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

        {/* Forward Kinematics Results */}
        {fkResult && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-gray-700/50 rounded-xl p-4 border border-gray-600"
          >
            <h4 className="text-sm font-semibold text-gray-300 mb-2 flex items-center">
              <Target className="w-4 h-4 mr-2" />
              End Effector Pose
            </h4>
            <div className="grid grid-cols-2 gap-4 text-xs">
              <div>
                <span className="text-gray-400">Position:</span>
                <div className="font-mono text-gray-200">
                  X: {fkResult.position[0]?.toFixed(3)}<br />
                  Y: {fkResult.position[1]?.toFixed(3)}<br />
                  Z: {fkResult.position[2]?.toFixed(3)}
                </div>
              </div>
              <div>
                <span className="text-gray-400">Orientation:</span>
                <div className="font-mono text-gray-200">
                  W: {fkResult.orientation[0]?.toFixed(3)}<br />
                  X: {fkResult.orientation[1]?.toFixed(3)}<br />
                  Y: {fkResult.orientation[2]?.toFixed(3)}<br />
                  Z: {fkResult.orientation[3]?.toFixed(3)}
                </div>
              </div>
            </div>
          </motion.div>
        )}

        <div className="flex gap-4 mt-auto">
          <AnimatedButton
            onClick={onCalculateFK}
            disabled={loading || !connected}
            size="md"
            className="flex-1"
            variant="secondary"
            leftIcon={<Target className="w-5 h-5" />}
          >
            {loading ? 'Calculating...' : 'Calculate FK'}
          </AnimatedButton>

          <AnimatedButton
            onClick={onExecuteMove}
            disabled={loading || !connected}
            size="md"
            className="flex-1"
            variant="success"
            leftIcon={<Play className="w-5 h-5" />}
          >
            {loading ? 'Executing...' : 'Execute'}
          </AnimatedButton>
        </div>
      </div>
    </motion.div>
  );
}