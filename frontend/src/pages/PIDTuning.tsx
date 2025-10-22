import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Settings, RotateCcw, Save } from 'lucide-react';

interface PIDValues {
  horizontal: {
    kp: number;
    ki: number;
    kd: number;
  };
  vertical: {
    kp: number;
    ki: number;
    kd: number;
  };
}

interface PIDSliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}

function PIDSlider({ label, value, min, max, step, onChange }: PIDSliderProps) {
  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-200">
        {label}: {value.toFixed(4)}
      </label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer slider"
      />
      <div className="flex justify-between text-xs text-gray-400">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}

export default function PIDTuning() {
  const [pidValues, setPidValues] = useState<PIDValues | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasChanges, setHasChanges] = useState(false);

  const fetchPIDValues = useCallback(async () => {
    try {
      const response = await fetch('http://localhost:5000/api/teleop/pid');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const data = await response.json();
      setPidValues(data.pid);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch PID values');
      setPidValues(null);
    }
  }, []);

  const updatePIDValue = useCallback(async (axis: 'horizontal' | 'vertical', param: 'kp' | 'ki' | 'kd', value: number) => {
    if (!pidValues) return;

    setLoading(true);
    try {
      const response = await fetch('http://localhost:5000/api/teleop/pid', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          axis,
          [param]: value,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      setPidValues(data.pid);
      setHasChanges(false);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update PID value');
    } finally {
      setLoading(false);
    }
  }, [pidValues]);

  const handleValueChange = useCallback((axis: 'horizontal' | 'vertical', param: 'kp' | 'ki' | 'kd', value: number) => {
    if (!pidValues) return;

    setPidValues(prev => prev ? {
      ...prev,
      [axis]: {
        ...prev[axis],
        [param]: value,
      },
    } : null);
    setHasChanges(true);
  }, [pidValues]);

  const resetToDefaults = useCallback(() => {
    // Reset to the tuned values we established earlier
    setPidValues({
      horizontal: { kp: 0.015, ki: 0.001, kd: 0.008 },
      vertical: { kp: 0.035, ki: 0.001, kd: 0.005 },
    });
    setHasChanges(true);
  }, []);

  useEffect(() => {
    fetchPIDValues();
    // Only poll for updates if there are no unsaved changes
    const interval = hasChanges ? null : setInterval(fetchPIDValues, 2000);
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [fetchPIDValues, hasChanges]);

  if (error && !pidValues) {
    return (
      <div className="min-h-screen bg-gray-900 text-white p-8">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-3xl font-bold mb-8">PID Tuning</h1>
          <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
            <p className="text-red-400">{error}</p>
            <p className="text-sm text-gray-400 mt-2">
              Make sure object-centering mode is active before using PID tuning.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <div className="max-w-4xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center space-x-3">
              <Settings className="w-8 h-8 text-blue-400" />
              <h1 className="text-3xl font-bold">PID Tuning</h1>
            </div>
            <div className="flex space-x-4">
              <button
                onClick={resetToDefaults}
                className="flex items-center space-x-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
              >
                <RotateCcw className="w-4 h-4" />
                <span>Reset to Defaults</span>
              </button>
              <button
                onClick={fetchPIDValues}
                className="flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors"
              >
                <Save className="w-4 h-4" />
                <span>Refresh</span>
              </button>
            </div>
          </div>

          {error && (
            <div className="bg-yellow-900/20 border border-yellow-500 rounded-lg p-4 mb-6">
              <p className="text-yellow-400">{error}</p>
            </div>
          )}

          {hasChanges && (
            <div className="bg-orange-900/20 border border-orange-500 rounded-lg p-4 mb-6">
              <p className="text-orange-400">You have unsaved changes. Polling paused to prevent slider reset.</p>
            </div>
          )}

          {pidValues ? (
            <div className="grid md:grid-cols-2 gap-8">
              {/* Horizontal PID */}
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.6, delay: 0.1 }}
                className="bg-gray-800/50 rounded-xl p-6 border border-gray-700/60"
              >
                <h2 className="text-xl font-semibold mb-6 text-blue-400">Horizontal Axis</h2>
                <div className="space-y-6">
                  <PIDSlider
                    label="Proportional (Kp)"
                    value={pidValues.horizontal.kp}
                    min={0}
                    max={0.1}
                    step={0.001}
                    onChange={(value) => handleValueChange('horizontal', 'kp', value)}
                  />
                  <PIDSlider
                    label="Integral (Ki)"
                    value={pidValues.horizontal.ki}
                    min={0}
                    max={0.01}
                    step={0.0001}
                    onChange={(value) => handleValueChange('horizontal', 'ki', value)}
                  />
                  <PIDSlider
                    label="Derivative (Kd)"
                    value={pidValues.horizontal.kd}
                    min={0}
                    max={0.02}
                    step={0.0001}
                    onChange={(value) => handleValueChange('horizontal', 'kd', value)}
                  />
                </div>
              </motion.div>

              {/* Vertical PID */}
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.6, delay: 0.2 }}
                className="bg-gray-800/50 rounded-xl p-6 border border-gray-700/60"
              >
                <h2 className="text-xl font-semibold mb-6 text-green-400">Vertical Axis</h2>
                <div className="space-y-6">
                  <PIDSlider
                    label="Proportional (Kp)"
                    value={pidValues.vertical.kp}
                    min={0}
                    max={0.1}
                    step={0.001}
                    onChange={(value) => handleValueChange('vertical', 'kp', value)}
                  />
                  <PIDSlider
                    label="Integral (Ki)"
                    value={pidValues.vertical.ki}
                    min={0}
                    max={0.01}
                    step={0.0001}
                    onChange={(value) => handleValueChange('vertical', 'ki', value)}
                  />
                  <PIDSlider
                    label="Derivative (Kd)"
                    value={pidValues.vertical.kd}
                    min={0}
                    max={0.02}
                    step={0.0001}
                    onChange={(value) => handleValueChange('vertical', 'kd', value)}
                  />
                </div>
              </motion.div>
            </div>
          ) : (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
              <span className="ml-3 text-gray-400">Loading PID values...</span>
            </div>
          )}

          {/* Apply Changes Button */}
          {hasChanges && pidValues && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-8 flex justify-center"
            >
              <button
                onClick={() => {
                  // Apply all changes
                  Object.entries(pidValues).forEach(([axis, params]) => {
                    Object.entries(params as Record<string, number>).forEach(([param, value]) => {
                      updatePIDValue(axis as 'horizontal' | 'vertical', param as 'kp' | 'ki' | 'kd', value);
                    });
                  });
                }}
                disabled={loading}
                className="flex items-center space-x-2 px-8 py-3 bg-green-600 hover:bg-green-500 disabled:bg-gray-600 rounded-lg transition-colors font-medium"
              >
                {loading ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                ) : (
                  <Save className="w-4 h-4" />
                )}
                <span>Apply All Changes</span>
              </button>
            </motion.div>
          )}

          {/* Instructions */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="mt-12 bg-gray-800/30 rounded-xl p-6 border border-gray-700/60"
          >
            <h3 className="text-lg font-semibold mb-4">PID Tuning Guide</h3>
            <div className="grid md:grid-cols-2 gap-6 text-sm text-gray-300">
              <div>
                <h4 className="font-medium text-blue-400 mb-2">Proportional (Kp)</h4>
                <p>Increases responsiveness. Too high causes oscillations.</p>
              </div>
              <div>
                <h4 className="font-medium text-green-400 mb-2">Integral (Ki)</h4>
                <p>Eliminates steady-state error. Too high causes instability.</p>
              </div>
              <div>
                <h4 className="font-medium text-purple-400 mb-2">Derivative (Kd)</h4>
                <p>Dampens oscillations. Too high makes movement sluggish.</p>
              </div>
              <div>
                <h4 className="font-medium text-orange-400 mb-2">Tips</h4>
                <p>Start with Ki=0, Kd=0. Increase Kp until oscillation, then add Kd to stabilize.</p>
              </div>
            </div>
          </motion.div>
        </motion.div>
      </div>
    </div>
  );
}