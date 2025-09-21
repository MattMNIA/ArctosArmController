import { useState } from 'react';
import { Home, CheckCircle, AlertCircle, Loader } from 'lucide-react';

export default function MotorHoming() {
  const [selectedMotors, setSelectedMotors] = useState<Set<number>>(new Set());
  const [homingStatus, setHomingStatus] = useState<Record<number, 'idle' | 'homing' | 'success' | 'error'>>({});
  const [isHomingAll, setIsHomingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const motors = [0, 1, 2, 3, 4, 5];

  const toggleMotor = (motorId: number) => {
    const newSelected = new Set(selectedMotors);
    if (newSelected.has(motorId)) {
      newSelected.delete(motorId);
    } else {
      newSelected.add(motorId);
    }
    setSelectedMotors(newSelected);
  };

  const selectAll = () => {
    setSelectedMotors(new Set(motors));
  };

  const clearAll = () => {
    setSelectedMotors(new Set());
  };

  const homeSelectedMotors = async () => {
    if (selectedMotors.size === 0) return;

    setError(null);
    setIsHomingAll(true);

    // Reset status for selected motors
    const newStatus = { ...homingStatus };
    selectedMotors.forEach(motor => {
      newStatus[motor] = 'homing';
    });
    setHomingStatus(newStatus);

    try {
      const response = await fetch('http://localhost:5000/api/execute/home_joints', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          joint_indices: Array.from(selectedMotors)
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      console.log('Homing result:', result);

      // Mark all selected motors as successful
      const successStatus = { ...newStatus };
      selectedMotors.forEach(motor => {
        successStatus[motor] = 'success';
      });
      setHomingStatus(successStatus);

    } catch (error) {
      console.error('Error homing motors:', error);
      setError(error instanceof Error ? error.message : 'Failed to home motors');

      // Mark all selected motors as failed
      const errorStatus = { ...newStatus };
      selectedMotors.forEach(motor => {
        errorStatus[motor] = 'error';
      });
      setHomingStatus(errorStatus);
    } finally {
      setIsHomingAll(false);
    }
  };

  const getStatusIcon = (motorId: number) => {
    const status = homingStatus[motorId] || 'idle';

    switch (status) {
      case 'homing':
        return <Loader className="w-5 h-5 text-blue-500 animate-spin" />;
      case 'success':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'error':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      default:
        return null;
    }
  };

  const getStatusColor = (motorId: number) => {
    const status = homingStatus[motorId] || 'idle';

    switch (status) {
      case 'homing':
        return 'border-blue-500 bg-blue-50 dark:bg-blue-900/20';
      case 'success':
        return 'border-green-500 bg-green-50 dark:bg-green-900/20';
      case 'error':
        return 'border-red-500 bg-red-50 dark:bg-red-900/20';
      default:
        return 'border-gray-300 dark:border-gray-600';
    }
  };

  return (
    <section className="py-8 min-h-screen">
      <div className="max-w-4xl mx-auto px-4">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold">Motor Homing Control</h1>
          <div className="flex space-x-2">
            <button
              onClick={selectAll}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold transition-colors duration-200"
            >
              Select All
            </button>
            <button
              onClick={clearAll}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg font-semibold transition-colors duration-200"
            >
              Clear All
            </button>
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <div className="bg-red-900/20 border border-red-800 rounded-2xl p-4 mb-6">
            <div className="flex items-center space-x-3">
              <AlertCircle className="w-5 h-5 text-red-400" />
              <div>
                <h3 className="font-semibold text-red-400">Homing Error</h3>
                <p className="text-red-300 text-sm">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Motor Selection Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          {motors.map((motorId) => (
            <div
              key={motorId}
              className={`border-2 rounded-lg p-4 cursor-pointer transition-all duration-200 hover:shadow-lg ${getStatusColor(motorId)}`}
              onClick={() => toggleMotor(motorId)}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-3">
                  <input
                    type="checkbox"
                    checked={selectedMotors.has(motorId)}
                    onChange={() => toggleMotor(motorId)}
                    className="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600"
                  />
                  <span className="font-semibold text-lg">Motor {motorId}</span>
                </div>
                {getStatusIcon(motorId)}
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Joint {motorId} homing control
              </p>
            </div>
          ))}
        </div>

        {/* Control Panel */}
        <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold mb-2">Homing Control</h2>
              <p className="text-gray-600 dark:text-gray-400">
                {selectedMotors.size === 0
                  ? 'Select motors to home'
                  : `${selectedMotors.size} motor${selectedMotors.size === 1 ? '' : 's'} selected for homing`
                }
              </p>
            </div>
            <button
              onClick={homeSelectedMotors}
              disabled={selectedMotors.size === 0 || isHomingAll}
              className="flex items-center space-x-3 px-6 py-3 bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white rounded-lg font-semibold transition-colors duration-200 disabled:cursor-not-allowed"
            >
              <Home className="w-5 h-5" />
              <span>
                {isHomingAll ? 'Homing Motors...' : 'Home Selected Motors'}
              </span>
              {isHomingAll && <Loader className="w-5 h-5 animate-spin" />}
            </button>
          </div>
        </div>

        {/* Instructions */}
        <div className="mt-8 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <h3 className="font-semibold text-blue-800 dark:text-blue-200 mb-2">Homing Instructions</h3>
          <ul className="text-sm text-blue-700 dark:text-blue-300 space-y-1">
            <li>• Select individual motors or use "Select All" to choose all motors</li>
            <li>• Click "Home Selected Motors" to start the homing process</li>
            <li>• Each motor will home sequentially using configured parameters</li>
            <li>• Green checkmarks indicate successful homing</li>
            <li>• Red warning icons indicate homing failures</li>
          </ul>
        </div>
      </div>
    </section>
  );
}