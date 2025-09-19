import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';

interface MotorCardProps {
  motorIndex: number;
  position: number; // in radians
  isEnabled: boolean;
  topLimitHit: boolean;
  bottomLimitHit: boolean;
  encoderError?: number; // encoder error in units
}

export default function MotorCard({
  motorIndex,
  position,
  isEnabled,
  topLimitHit,
  bottomLimitHit,
  encoderError = 0
}: MotorCardProps) {
  const positionDegrees = (position * 180 / Math.PI).toFixed(1);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay: motorIndex * 0.1 }}
      whileHover={{ scale: 1.02, y: -5 }}
      className="group relative bg-gray-800 rounded-3xl shadow-lg border border-gray-700/50 p-8 hover:shadow-xl hover:shadow-gray-900/25 transition-all duration-300 ease-out"
    >
      {/* Header Section */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          <motion.div 
            whileHover={{ scale: 1.1, rotate: 5 }}
            className="w-10 h-10 bg-blue-500 rounded-2xl flex items-center justify-center shadow-sm"
          >
            <span className="text-white font-bold text-sm">
              {motorIndex + 1}
            </span>
          </motion.div>
          <div>
            <h3 className="text-xl font-bold text-white leading-tight">
              Motor {motorIndex + 1}
            </h3>
            <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">
              Joint Controller
            </p>
          </div>
        </div>

        {/* Status Indicator */}
        <div className="flex flex-col items-end space-y-1">
          <motion.div 
            animate={isEnabled ? { scale: [1, 1.2, 1] } : {}}
            transition={{ duration: 2, repeat: Infinity }}
            className={`w-4 h-4 rounded-full shadow-sm ring-2 ${
              isEnabled
                ? 'bg-green-400 ring-green-800'
                : 'bg-gray-600 ring-gray-700'
            }`} 
          />
          <span className={`text-xs font-semibold ${
            isEnabled 
              ? 'text-green-400' 
              : 'text-gray-400'
          }`}>
            {isEnabled ? 'Active' : 'Inactive'}
          </span>
        </div>
      </div>

      {/* Position Section */}
      <div className="bg-gray-900/50 rounded-2xl p-4 mb-6 border border-gray-700/50">
        <div>
          <p className="text-sm font-semibold text-gray-400 mb-1">Current Position</p>
          <div className="text-3xl font-black text-white tracking-tight">
            {positionDegrees}°
          </div>
        </div>
      </div>

      {/* Encoder Error Section */}
      <div className="bg-gray-900/50 rounded-2xl p-4 mb-6 border border-gray-700/50">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-gray-400 mb-1">Encoder Error</p>
            <div className={`text-2xl font-bold tracking-tight ${
              Math.abs(encoderError) >= 1000 
                ? 'text-red-400' 
                : Math.abs(encoderError) >= 100 
                  ? 'text-yellow-400' 
                  : 'text-green-400'
            }`}>
              {encoderError > 0 ? '+' : ''}{encoderError} units
            </div>
          </div>
          <motion.div 
            animate={Math.abs(encoderError) >= 100 ? { scale: [1, 1.2, 1] } : {}}
            transition={{ duration: 2, repeat: Math.abs(encoderError) >= 100 ? Infinity : 0 }}
            className="w-12 h-12 bg-gray-900/30 rounded-xl flex items-center justify-center"
          >
            <AlertTriangle className={`w-6 h-6 ${
              Math.abs(encoderError) >= 1000 
                ? 'text-red-400' 
                : Math.abs(encoderError) >= 100 
                  ? 'text-yellow-400' 
                  : 'text-green-400'
            }`} />
          </motion.div>
        </div>
      </div>

      {/* Limits Section */}
      <div className="space-y-3">
        <p className="text-sm font-semibold text-gray-400">Limit Switches</p>
        <div className="grid grid-cols-2 gap-3">
          {/* Top Limit */}
          <motion.div 
            whileHover={{ scale: 1.05 }}
            className="bg-gray-900/50 rounded-xl p-3 border border-gray-700 shadow-sm"
          >
            <div className="flex items-center space-x-3">
              <motion.div 
                animate={topLimitHit ? { scale: [1, 1.2, 1] } : {}}
                transition={{ duration: 1.5, repeat: Infinity }}
                className={`w-5 h-5 rounded-full shadow-sm ring-2 ring-gray-800 transition-all duration-200 ${
                  topLimitHit
                    ? 'bg-green-500 shadow-green-900'
                    : 'bg-red-400 shadow-red-900'
                }`} 
              />
              <div>
                <p className="text-sm font-semibold text-gray-100">Top</p>
                <p className={`text-xs font-medium ${
                  topLimitHit 
                    ? 'text-green-400' 
                    : 'text-red-400'
                }`}>
                  {topLimitHit ? 'Hit' : 'Clear'}
                </p>
              </div>
            </div>
          </motion.div>

          {/* Bottom Limit */}
          <motion.div 
            whileHover={{ scale: 1.05 }}
            className="bg-gray-900/50 rounded-xl p-3 border border-gray-700 shadow-sm"
          >
            <div className="flex items-center space-x-3">
              <motion.div 
                animate={bottomLimitHit ? { scale: [1, 1.2, 1] } : {}}
                transition={{ duration: 1.5, repeat: Infinity }}
                className={`w-5 h-5 rounded-full shadow-sm ring-2 ring-gray-800 transition-all duration-200 ${
                  bottomLimitHit
                    ? 'bg-green-500 shadow-green-900'
                    : 'bg-red-400 shadow-red-900'
                }`} 
              />
              <div>
                <p className="text-sm font-semibold text-gray-100">Bottom</p>
                <p className={`text-xs font-medium ${
                  bottomLimitHit 
                    ? 'text-green-400' 
                    : 'text-red-400'
                }`}>
                  {bottomLimitHit ? 'Hit' : 'Clear'}
                </p>
              </div>
            </div>
          </motion.div>
        </div>
      </div>

      {/* Subtle gradient overlay for depth */}
      <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent rounded-3xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
    </motion.div>
  );
}