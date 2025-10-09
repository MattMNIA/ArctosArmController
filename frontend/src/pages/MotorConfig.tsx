import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { RotateCcw, Settings, Save } from 'lucide-react';

interface MotorConfig {
  id: number;
  speed_rpm: number;
  acceleration: number;
  homing_offset: number;
  home_direction: string;
  home_speed: number;
  offset_speed: number;
  endstop_level: string;
}

export default function MotorConfig() {
  const [motors, setMotors] = useState<MotorConfig[]>([]);
  const [originalMotors, setOriginalMotors] = useState<MotorConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    fetchMotors();
  }, []);

  const fetchMotors = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/config/motors');
      if (!response.ok) throw new Error('Failed to fetch motor configurations');
      const data = await response.json();
      setMotors(data);
      setOriginalMotors(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load configurations');
    } finally {
      setLoading(false);
    }
  };

  const updateMotor = async (motorId: number, field: keyof MotorConfig, value: number | string) => {
    try {
      const response = await fetch(`/api/config/motors/${motorId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          [field]: value
        }),
      });

      if (!response.ok) throw new Error('Failed to update motor configuration');

      // Update original state
      setOriginalMotors(prev => prev.map(motor =>
        motor.id === motorId ? { ...motor, [field]: value } : motor
      ));
    } catch (err) {
      throw err;
    }
  };

  const saveChanges = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      const promises: Promise<void>[] = [];
      motors.forEach(motor => {
        const original = originalMotors.find(o => o.id === motor.id);
        if (original) {
          const originalSpeed = original.speed_rpm;
          const originalSpeedSign = originalSpeed === 0 ? 1 : Math.sign(originalSpeed);
          const currentSpeed = motor.speed_rpm;
          if (Math.abs(currentSpeed) !== Math.abs(originalSpeed)) {
            const signedSpeed = originalSpeedSign * Math.abs(currentSpeed);
            promises.push(updateMotor(motor.id, 'speed_rpm', signedSpeed));
          }
          if (motor.acceleration !== original.acceleration) {
            promises.push(updateMotor(motor.id, 'acceleration', motor.acceleration));
          }
          if (motor.homing_offset !== original.homing_offset) {
            promises.push(updateMotor(motor.id, 'homing_offset', motor.homing_offset));
          }
          if (motor.home_direction !== original.home_direction) {
            promises.push(updateMotor(motor.id, 'home_direction', motor.home_direction));
          }
          if (motor.home_speed !== original.home_speed) {
            promises.push(updateMotor(motor.id, 'home_speed', motor.home_speed));
          }
          if (motor.offset_speed !== original.offset_speed) {
            promises.push(updateMotor(motor.id, 'offset_speed', motor.offset_speed));
          }
          if (motor.endstop_level !== original.endstop_level) {
            promises.push(updateMotor(motor.id, 'endstop_level', motor.endstop_level));
          }
        }
      });

      await Promise.all(promises);

      setSuccess('All changes saved successfully');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save configurations');
    } finally {
      setSaving(false);
    }
  };

  const resetToDefaults = () => {
    // Reset to default values (you might want to fetch these from the server)
    const defaultMotors: MotorConfig[] = [
      { id: 0, speed_rpm: 200, acceleration: 50, homing_offset: 103000, home_direction: 'CCW', home_speed: 50, offset_speed: 100, endstop_level: 'Low' },
      { id: 1, speed_rpm: 20, acceleration: 10, homing_offset: 236000, home_direction: 'CCW', home_speed: 50, offset_speed: 100, endstop_level: 'Low' },
      { id: 2, speed_rpm: 200, acceleration: 50, homing_offset: 238796, home_direction: 'CCW', home_speed: 50, offset_speed: 100, endstop_level: 'Low' },
      { id: 3, speed_rpm: 200, acceleration: 50, homing_offset: 203333, home_direction: 'CCW', home_speed: 50, offset_speed: 100, endstop_level: 'Low' },
      { id: 4, speed_rpm: 500, acceleration: 40, homing_offset: 25000, home_direction: 'CCW', home_speed: 50, offset_speed: 100, endstop_level: 'Low' },
      { id: 5, speed_rpm: 500, acceleration: 40, homing_offset: 20000, home_direction: 'CCW', home_speed: 50, offset_speed: 100, endstop_level: 'Low' },
    ];
    setMotors(defaultMotors);
    setOriginalMotors(defaultMotors);
  };

  const hasChanges = motors.some(motor => {
    const original = originalMotors.find(o => o.id === motor.id);
    return original && (
      Math.abs(motor.speed_rpm) !== Math.abs(original.speed_rpm) ||
      motor.acceleration !== original.acceleration ||
      motor.homing_offset !== original.homing_offset ||
      motor.home_direction !== original.home_direction ||
      motor.home_speed !== original.home_speed ||
      motor.offset_speed !== original.offset_speed ||
      motor.endstop_level !== original.endstop_level
    );
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-6xl mx-auto p-6"
    >
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
          <Settings className="w-8 h-8 text-blue-400" />
          Motor Configuration
        </h1>
        <p className="text-gray-400">
          Configure speed, acceleration, and homing settings for each motor
        </p>
      </div>

      {error && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mb-6 p-4 bg-red-900/20 border border-red-500/50 rounded-lg"
        >
          <p className="text-red-400">{error}</p>
        </motion.div>
      )}

      {success && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mb-6 p-4 bg-green-900/20 border border-green-500/50 rounded-lg"
        >
          <p className="text-green-400">{success}</p>
        </motion.div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {motors.map((motor) => (
          <motion.div
            key={motor.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: motor.id * 0.1 }}
            className="bg-gray-800/50 backdrop-blur-sm rounded-xl p-6 border border-gray-700/50"
          >
            <h3 className="text-xl font-semibold text-white mb-4">
              Motor {motor.id + 1}
            </h3>

            <div className="space-y-4">
              {/* Speed RPM */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Speed (RPM)
                </label>
                <input
                  type="number"
                  value={Math.abs(motor.speed_rpm)}
                  onChange={(e) => {
                    const value = parseInt(e.target.value, 10);
                    const magnitude = Number.isNaN(value) ? 0 : Math.abs(value);
                    setMotors(prev => prev.map(m => {
                      if (m.id !== motor.id) return m;
                      const currentOriginal = originalMotors.find(o => o.id === motor.id);
                      const signSource = currentOriginal?.speed_rpm ?? m.speed_rpm;
                      const sign = signSource === 0 ? 1 : Math.sign(signSource);
                      return { ...m, speed_rpm: sign * magnitude };
                    }));
                  }}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  min="1"
                  max="1000"
                />
              </div>

              {/* Acceleration */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Acceleration
                </label>
                <input
                  type="number"
                  value={motor.acceleration}
                  onChange={(e) => {
                    const value = parseInt(e.target.value) || 0;
                    setMotors(prev => prev.map(m =>
                      m.id === motor.id ? { ...m, acceleration: value } : m
                    ));
                  }}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  min="1"
                  max="1000"
                />
              </div>

              {/* Homing Offset */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Homing Offset
                </label>
                <input
                  type="number"
                  value={motor.homing_offset}
                  onChange={(e) => {
                    const value = parseInt(e.target.value) || 0;
                    setMotors(prev => prev.map(m =>
                      m.id === motor.id ? { ...m, homing_offset: value } : m
                    ));
                  }}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* Home Direction */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Home Direction
                </label>
                <select
                  value={motor.home_direction}
                  onChange={(e) => {
                    setMotors(prev => prev.map(m =>
                      m.id === motor.id ? { ...m, home_direction: e.target.value } : m
                    ));
                  }}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="CW">CW</option>
                  <option value="CCW">CCW</option>
                </select>
              </div>

              {/* Home Speed */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Home Speed
                </label>
                <input
                  type="number"
                  value={motor.home_speed}
                  onChange={(e) => {
                    const value = parseInt(e.target.value) || 0;
                    setMotors(prev => prev.map(m =>
                      m.id === motor.id ? { ...m, home_speed: value } : m
                    ));
                  }}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  min="1"
                  max="1000"
                />
              </div>

              {/* Offset Speed */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Offset Speed
                </label>
                <input
                  type="number"
                  value={motor.offset_speed}
                  onChange={(e) => {
                    const value = parseInt(e.target.value) || 0;
                    setMotors(prev => prev.map(m =>
                      m.id === motor.id ? { ...m, offset_speed: value } : m
                    ));
                  }}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  min="1"
                  max="1000"
                />
              </div>

              {/* Endstop Level */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Endstop Level
                </label>
                <select
                  value={motor.endstop_level}
                  onChange={(e) => {
                    setMotors(prev => prev.map(m =>
                      m.id === motor.id ? { ...m, endstop_level: e.target.value } : m
                    ));
                  }}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="Low">Low</option>
                  <option value="High">High</option>
                </select>
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      <div className="flex justify-center gap-4">
        <motion.button
          onClick={saveChanges}
          disabled={!hasChanges || saving}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 text-white rounded-lg transition-colors duration-200"
        >
          <Save className="w-5 h-5" />
          Save Changes
        </motion.button>
        <motion.button
          onClick={resetToDefaults}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="flex items-center gap-2 px-6 py-3 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors duration-200"
        >
          <RotateCcw className="w-5 h-5" />
          Reset to Defaults
        </motion.button>
      </div>

      {saving && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 p-6 rounded-lg flex items-center gap-3">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
            <span className="text-white">Saving configuration...</span>
          </div>
        </div>
      )}
    </motion.div>
  );
}