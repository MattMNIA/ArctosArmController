import { useState, useEffect, useRef } from 'react';
import { Home, CheckCircle, AlertCircle, Loader, Save } from 'lucide-react';
import io, { Socket } from 'socket.io-client';

export default function MotorHoming() {
  const [selectedMotors, setSelectedMotors] = useState<Set<number>>(new Set());
  const [homingStatus, setHomingStatus] = useState<Record<number, 'idle' | 'homing' | 'success' | 'error'>>({});
  const [isHomingAll, setIsHomingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [encoderValues, setEncoderValues] = useState<Record<number, number>>({});
  const [jointAngles, setJointAngles] = useState<Record<number, number>>({});
  const [adjustingMotors, setAdjustingMotors] = useState<Set<number>>(new Set());
  const [isAdjusting, setIsAdjusting] = useState(false);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<Socket | null>(null);

  const motors = [0, 1, 2, 3, 4, 5];

  useEffect(() => {
    // WebSocket connection for real-time telemetry
    const socket = io('http://localhost:5000', {
      transports: ['websocket', 'polling'],
      timeout: 5000,
      forceNew: true
    });

    socketRef.current = socket;

    socket.on('connect', () => {
      setConnected(true);
    });

    socket.on('disconnect', () => {
      setConnected(false);
    });

    socket.on('telemetry', (data: any) => {
      // Update encoder values from telemetry
      if (data.encoders && Array.isArray(data.encoders)) {
        const newEncoders: Record<number, number> = {};
        data.encoders.forEach((encoder: number, index: number) => {
          newEncoders[index] = encoder;
        });
        setEncoderValues(newEncoders);
      }
      
      // Update joint angles from telemetry
      if (data.q && Array.isArray(data.q)) {
        const newAngles: Record<number, number> = {};
        data.q.forEach((angle: number, index: number) => {
          newAngles[index] = angle;
        });
        setJointAngles(newAngles);
      }
    });

    socket.on('connect_error', (err) => {
      console.error('WebSocket connection error:', err);
      setConnected(false);
    });

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, []);

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

  const moveByDegrees = async (jointIndex: number, degrees: number) => {
    setIsAdjusting(true);
    try {
      // Get current joint angle
      const currentAngle = jointAngles[jointIndex] || 0;
      
      // Calculate new angle (convert degrees to radians)
      const degreesInRadians = (degrees * Math.PI) / 180;
      const newAngle = currentAngle + degreesInRadians;
      
      // Create joint command with all current positions, but update the target joint
      const jointPositions = [0, 1, 2, 3, 4, 5].map(i => jointAngles[i] || 0);
      jointPositions[jointIndex] = newAngle;
      
      const response = await fetch('http://localhost:5000/api/execute/joints', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          q: jointPositions,
          duration_s: 0.5
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      console.log('Move by degrees result:', result);
      // Joint positions will be updated automatically via WebSocket telemetry
    } catch (error) {
      console.error('Error moving by degrees:', error);
      setError(error instanceof Error ? error.message : 'Failed to move by degrees');
    } finally {
      setIsAdjusting(false);
    }
  };

  const saveOffset = async (jointIndex: number) => {
    try {
      const response = await fetch('http://localhost:5000/api/execute/save_offset', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          joint_index: jointIndex
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      console.log('Offset saved:', result);
      alert(`Offset saved for Motor ${jointIndex}: ${result.offset_encoder} encoder units`);
    } catch (error) {
      console.error('Error saving offset:', error);
      setError(error instanceof Error ? error.message : 'Failed to save offset');
    }
  };

  const toggleAdjustment = (motorId: number) => {
    const newAdjusting = new Set(adjustingMotors);
    if (newAdjusting.has(motorId)) {
      newAdjusting.delete(motorId);
    } else {
      newAdjusting.add(motorId);
    }
    setAdjustingMotors(newAdjusting);
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
              className={`border-2 rounded-lg p-4 transition-all duration-200 hover:shadow-lg ${getStatusColor(motorId)}`}
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
              
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Joint {motorId} homing control
              </p>
              
              {/* Encoder value display */}
              {encoderValues[motorId] !== undefined && (
                <p className="text-xs text-gray-500 dark:text-gray-500 mb-2">
                  Encoder: {encoderValues[motorId]}
                </p>
              )}
              
              {/* Adjustment controls for successfully homed motors */}
              {homingStatus[motorId] === 'success' && (
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-600">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium">Offset Adjustment</span>
                    <button
                      onClick={() => toggleAdjustment(motorId)}
                      className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 rounded"
                    >
                      {adjustingMotors.has(motorId) ? 'Hide' : 'Adjust'}
                    </button>
                  </div>
                  
                  {adjustingMotors.has(motorId) && (
                    <div className="space-y-2">
                      <div className="flex items-center space-x-2">
                        <input
                          type="number"
                          placeholder="Degrees to move (+/-)"
                          className="flex-1 px-2 py-1 text-sm border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                          id={`degree-input-${motorId}`}
                        />
                        <button
                          onClick={() => {
                            const input = document.getElementById(`degree-input-${motorId}`) as HTMLInputElement;
                            const degrees = parseFloat(input.value);
                            if (!isNaN(degrees)) {
                              moveByDegrees(motorId, degrees);
                            }
                          }}
                          disabled={isAdjusting}
                          className="px-3 py-1 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm rounded font-medium"
                        >
                          Move
                        </button>
                      </div>
                      <button
                        onClick={() => saveOffset(motorId)}
                        className="w-full flex items-center justify-center space-x-2 px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded font-medium"
                      >
                        <Save className="w-4 h-4" />
                        <span>Save Offset</span>
                      </button>
                    </div>
                  )}
                </div>
              )}
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
            <li>• After homing, click "Adjust" on successfully homed motors to fine-tune position</li>
            <li>• Enter degrees to move (+/-) and click "Move" to adjust the motor position</li>
            <li>• Click "Save Offset" to save the current position as the new homing offset</li>
          </ul>
        </div>
      </div>
    </section>
  );
}