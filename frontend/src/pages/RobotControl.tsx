import { useState, useCallback, useEffect, useRef } from "react";
import { motion } from 'framer-motion';
import { AlertCircle, RefreshCw, Calculator, Play } from 'lucide-react';
import type { Socket } from 'socket.io-client';
import JointControl from '../components/JointControl';
import GripperControl from '../components/GripperControl';
import { AnimatedButton } from '../components/ui/AnimatedButton';
import { ConnectionIndicator } from '../components/ui/ConnectionIndicator';
import { AlertBanner } from '../components/ui/AlertBanner';
import { PageHeader } from '../components/layout/PageHeader';
import { useSocketConnection } from '../hooks/useSocketConnection';

export default function RobotControl() {
  const [msg, setMsg] = useState("Connecting...");
  const [jointInputs, setJointInputs] = useState<string[]>(['0','0','0','0','0','0']);
  const [gripperInput, setGripperInput] = useState<string>('0.0');
  const [loading, setLoading] = useState(false);
  const [fkResult, setFkResult] = useState<{ position: number[]; orientation: number[] } | null>(null);
  const [robotState, setRobotState] = useState<any>(null);
  const inputsInitializedRef = useRef(false);
  const [ikPosition, setIkPosition] = useState<string[]>(['0.3', '0.1', '0.2']);
  const [ikOrientation, setIkOrientation] = useState<string[]>(['0', '0', '0', '1']);
  const [solvedJoints, setSolvedJoints] = useState<number[] | null>(null);

  const { status: connectionStatus, reconnect } = useSocketConnection('http://localhost:5000', {
    registerHandlers: useCallback((socket: Socket) => {
      const handleStatus = (data: { msg: string }) => {
        setMsg(data.msg);
      };

      const handleTelemetry = (data: any) => {
        setRobotState(data);
        if (data.q && data.q.length > 0 && !inputsInitializedRef.current) {
          // Convert radians to degrees for display
          const jointsDegrees = data.q.map((j: number) => (j * 180 / Math.PI).toFixed(2).toString());
          setJointInputs(jointsDegrees);
          inputsInitializedRef.current = true;
        }
        if (data.gripper_position !== undefined) {
          setGripperInput(data.gripper_position.toString());
        }
      };

      socket.on('status', handleStatus);
      socket.on('telemetry', handleTelemetry);
      
      return () => {
        socket.off('status', handleStatus);
        socket.off('telemetry', handleTelemetry);
      };
    }, []),
    onConnect: () => setMsg('Connected to backend'),
    onDisconnect: () => setMsg('Disconnected from backend'),
    onConnectError: () => {
      setMsg('Connection failed');
      return 'Failed to connect to backend server. Please ensure the backend is running.';
    },
  });

  const { connected, loading: connectionLoading, reconnecting, error: connectionError } = connectionStatus;

  useEffect(() => {
    if (connectionLoading) {
      setMsg('Connecting...');
    }
  }, [connectionLoading]);

  const sendIK = async () => {
    setLoading(true);
    try {
      const position = ikPosition.map(p => parseFloat(p) || 0);
      const orientation = ikOrientation.map(o => parseFloat(o) || 0);
      const seed = jointInputs.map(j => parseFloat(j) || 0).map(j => j * Math.PI / 180);
      const res = await fetch("http://localhost:5000/api/ik/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          pose: { position, orientation }, 
          seed
        })
      });
      const data = await res.json();
      const newJoints = (data.joints as number[]).map((j: number) => j * 180 / Math.PI);
      setSolvedJoints(newJoints);
    } catch (error) {
      console.error("IK solve failed:", error);
    } finally {
      setLoading(false);
    }
  };

  const calculateFK = async () => {
    setLoading(true);
    try {
      const jointValues = jointInputs.map(j => parseFloat(j) || 0);
      const res = await fetch("http://localhost:5000/api/ik/fk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          joints: jointValues.map((j: number) => j * Math.PI / 180) 
        })
      });
      const data = await res.json();
      if (data.position && data.orientation) {
        setFkResult({
          position: data.position,
          orientation: data.orientation
        });
      } else {
        console.error("Invalid FK response:", data);
      }
    } catch (error) {
      console.error("FK calculation failed:", error);
    } finally {
      setLoading(false);
    }
  };

  const executeMove = async () => {
    setLoading(true);
    try {
      const jointValues = jointInputs.map(j => parseFloat(j) || 0);
      await fetch("http://localhost:5000/api/execute/joints", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q: jointValues.map((j: number) => j * Math.PI / 180) })
      });
    } catch (error) {
      console.error("Execute move failed:", error);
    } finally {
      setLoading(false);
    }
  };

  const executeSolvedIK = async () => {
    if (!solvedJoints) return;
    setLoading(true);
    try {
      await fetch("http://localhost:5000/api/execute/joints", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q: solvedJoints.map((j: number) => j * Math.PI / 180) })
      });
    } catch (error) {
      console.error("Execute solved IK failed:", error);
    } finally {
      setLoading(false);
    }
  };

  const openGripper = async () => {
    try {
      const res = await fetch("http://localhost:5000/api/execute/open_gripper", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) {
        alert("Failed to open gripper");
      }
    } catch (error) {
      alert("Error opening gripper");
    }
  };

  const closeGripper = async () => {
    try {
      const res = await fetch("http://localhost:5000/api/execute/close_gripper", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) {
        alert("Failed to close gripper");
      }
    } catch (error) {
      alert("Error closing gripper");
    }
  };

  const setGripper = async () => {
    try {
      const position = parseFloat(gripperInput) || 0;
      const res = await fetch("http://localhost:5000/api/execute/set_gripper_position", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position }),
      });
      if (!res.ok) {
        alert("Failed to set gripper position");
      }
    } catch (error) {
      alert("Error setting gripper position");
    }
  };

  const emergencyStop = async () => {
    try {
      const confirmed = window.confirm("Are you sure you want to EMERGENCY STOP all motors? This will immediately halt all movement.");
      if (!confirmed) return;

      const res = await fetch("http://localhost:5000/api/execute/estop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) {
        alert("Failed to execute emergency stop");
      } else {
        alert("Emergency stop executed successfully");
      }
    } catch (error) {
      alert("Error executing emergency stop");
    }
  };

  return (
    <section className="py-8 min-h-screen">
      <div className="max-w-6xl mx-auto px-6">
        <PageHeader
          title="Robotic Arm Control Center"
          description="Precision control interface for joint positioning and gripper operations"
          centered
          statusSlot={
            <ConnectionIndicator
              connected={connected}
              connectedLabel={msg}
              disconnectedLabel={msg}
            />
          }
        />

        <div className="flex flex-col items-center mb-12">
          <AnimatedButton
            variant="danger"
            size="lg"
            onClick={emergencyStop}
            leftIcon={<AlertCircle className="w-5 h-5" />}
          >
            EMERGENCY STOP
          </AnimatedButton>
          <p className="text-xs text-red-400 mt-2 text-center">
            Immediately stops all motors - use only in emergency
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-8">
          {/* Joint Control Section */}
          <JointControl
            jointInputs={jointInputs}
            setJointInputs={setJointInputs}
            connected={connected}
            loading={loading}
            onCalculateFK={calculateFK}
            onExecuteMove={executeMove}
            fkResult={fkResult}
          />

          <GripperControl
            gripperInput={gripperInput}
            setGripperInput={setGripperInput}
            connected={connected}
            onOpenGripper={openGripper}
            onCloseGripper={closeGripper}
            onSetGripper={setGripper}
          />
        </div>

        {/* IK Solving Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="bg-gray-800 rounded-3xl shadow-lg border border-gray-700/50 p-6 mt-8"
        >
          <h2 className="text-xl font-semibold mb-4">Inverse Kinematics Solver</h2>
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <h3 className="text-sm font-semibold text-gray-300 mb-2">Target Position (m)</h3>
              <div className="space-y-2">
                {['X', 'Y', 'Z'].map((axis, index) => (
                  <div key={axis} className="flex items-center space-x-2">
                    <label className="text-sm text-gray-400 w-6">{axis}:</label>
                    <input
                      type="number"
                      step="0.01"
                      value={ikPosition[index]}
                      onChange={(e) => {
                        const newPos = [...ikPosition];
                        newPos[index] = e.target.value;
                        setIkPosition(newPos);
                      }}
                      className="flex-1 px-3 py-2 rounded-lg border border-gray-600 bg-gray-700 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-300 mb-2">Target Orientation (quaternion)</h3>
              <div className="space-y-2">
                {['W', 'X', 'Y', 'Z'].map((comp, index) => (
                  <div key={comp} className="flex items-center space-x-2">
                    <label className="text-sm text-gray-400 w-6">{comp}:</label>
                    <input
                      type="number"
                      step="0.01"
                      value={ikOrientation[index]}
                      onChange={(e) => {
                        const newOri = [...ikOrientation];
                        newOri[index] = e.target.value;
                        setIkOrientation(newOri);
                      }}
                      className="flex-1 px-3 py-2 rounded-lg border border-gray-600 bg-gray-700 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
          {solvedJoints && (
            <div className="mt-4 p-4 bg-gray-700/50 rounded-xl">
              <h4 className="text-sm font-semibold text-gray-300 mb-2">Solved Joint Angles (°)</h4>
              <div className="grid grid-cols-6 gap-2 text-xs">
                {solvedJoints.map((angle, index) => (
                  <div key={index} className="text-center">
                    <span className="text-gray-400">J{index + 1}:</span>
                    <div className="font-mono text-gray-200">{angle.toFixed(2)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="flex gap-4 mt-6">
            <AnimatedButton
              onClick={sendIK}
              disabled={loading || !connected}
              size="md"
              leftIcon={<Calculator className="w-5 h-5" />}
            >
              {loading ? 'Solving...' : 'Solve IK'}
            </AnimatedButton>
            <AnimatedButton
              onClick={executeSolvedIK}
              disabled={loading || !connected || !solvedJoints}
              size="md"
              variant="success"
              leftIcon={<Play className="w-5 h-5" />}
            >
              {loading ? 'Executing...' : 'Execute Solved Pose'}
            </AnimatedButton>
          </div>
        </motion.div>

        {connectionError && (
          <AlertBanner
            variant="error"
            title="Connection Error"
            message={
              <>
                <p>{connectionError}</p>
                <p className="text-xs mt-2">
                  Please ensure the backend server is running to control the robotic arm.
                </p>
              </>
            }
            action={{
              label: reconnecting ? 'Reconnecting...' : 'Retry Connection',
              onClick: reconnect,
              icon: <RefreshCw className="w-4 h-4" />,
              loading: reconnecting,
            }}
            className="mt-8"
          />
        )}

        {!connected && !connectionError && !connectionLoading && (
          <AlertBanner
            variant="warning"
            title="Connection Required"
            message="Attempting to connect to backend server..."
            className="mt-8"
          />
        )}
      </div>
    </section>
  );
}
