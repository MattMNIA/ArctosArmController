import { useState, useEffect, useRef } from "react";
import { motion } from 'framer-motion';
import { Grip, Hand, Wifi, WifiOff, AlertCircle, RefreshCw } from 'lucide-react';
import io, { Socket } from "socket.io-client";
import JointControl from '../components/JointControl';

export default function RobotControl() {
  const [msg, setMsg] = useState("Connecting...");
  const [jointInputs, setJointInputs] = useState<string[]>(['0','0','0','0','0','0']);
  const [gripperInput, setGripperInput] = useState<string>('0.0');
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const socketRef = useRef<Socket | null>(null);

  const connectToSocket = () => {
    // Disconnect existing socket if any
    if (socketRef.current) {
      socketRef.current.disconnect();
    }

    setReconnecting(true);
    setConnectionError(null);
    setMsg("Connecting...");

    const socket = io("http://localhost:5000", {
      transports: ['websocket', 'polling'],
      timeout: 5000,
      forceNew: true
    });

    socketRef.current = socket;

    socket.on("connect", () => {
      setMsg("Connected to backend");
      setConnected(true);
      setConnectionError(null);
      setReconnecting(false);
    });

    socket.on("disconnect", (reason) => {
      setConnected(false);
      setConnectionError(`Disconnected: ${reason}`);
      setMsg("Disconnected from backend");
      setReconnecting(false);
    });

    socket.on("connect_error", (err) => {
      setConnected(false);
      setConnectionError("Failed to connect to backend server");
      setMsg("Connection failed");
      setReconnecting(false);
    });

    socket.on("status", (data: any) => setMsg(data.msg));

    // Set a timeout for connection attempt
    setTimeout(() => {
      if (!socket.connected) {
        setConnectionError("Connection timeout. Backend server may not be running.");
        setReconnecting(false);
      }
    }, 10000);
  };

  useEffect(() => {
    connectToSocket();

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, []);

  const sendIK = async () => {
    setLoading(true);
    try {
      const jointValues = jointInputs.map(j => parseFloat(j) || 0);
      const res = await fetch("http://localhost:5000/api/ik/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          pose: { position: [0.3, 0.1, 0.2], orientation: [0,0,0,1] }, 
          seed: jointValues.map((j: number) => j * Math.PI / 180) 
        })
      });
      const data = await res.json();
      const newJoints = (data.joints as number[]).map((j: number) => j * 180 / Math.PI);
      setJointInputs(newJoints.map(j => j.toString()));
    } catch (error) {
      console.error("IK solve failed:", error);
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
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="text-center mb-12"
        >
          <h1 className="text-3xl md:text-4xl font-bold mb-4">
            <span className="text-white">
              Robotic Arm Control Center
            </span>
          </h1>
          <div className="h-1 w-20 bg-blue-500 mx-auto mb-6 rounded-full"></div>
          
          {/* Connection Status */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="flex items-center justify-center space-x-2 mb-6"
          >
            {connected ? (
              <>
                <Wifi className="w-5 h-5 text-green-400" />
                <span className="text-sm font-semibold text-green-400">
                  {msg}
                </span>
              </>
            ) : (
              <>
                <WifiOff className="w-5 h-5 text-red-400" />
                <span className="text-sm font-semibold text-red-400">
                  Disconnected
                </span>
              </>
            )}
          </motion.div>

          {/* Emergency Stop Button */}
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.4 }}
            className="mb-8"
          >
            <motion.button
              onClick={emergencyStop}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="flex items-center justify-center space-x-3 px-8 py-4 bg-red-600 hover:bg-red-700 text-white rounded-2xl font-bold text-lg shadow-lg hover:shadow-xl transition-all duration-200 border-2 border-red-500"
            >
              <AlertCircle className="w-6 h-6" />
              <span>EMERGENCY STOP</span>
            </motion.button>
            <p className="text-xs text-red-400 mt-2 text-center">
              Immediately stops all motors - use only in emergency
            </p>
          </motion.div>

          <p className="text-lg text-gray-300 max-w-2xl mx-auto">
            Precision control interface for joint positioning and gripper operations
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-8">
          {/* Joint Control Section */}
          <JointControl
            jointInputs={jointInputs}
            setJointInputs={setJointInputs}
            connected={connected}
            loading={loading}
            onSolveIK={sendIK}
            onExecuteMove={executeMove}
          />

          {/* Gripper Control Section */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.4 }}
            className="bg-gray-800 rounded-3xl shadow-lg border border-gray-700/50 p-8"
          >
            <div className="flex items-center space-x-3 mb-6">
              <motion.div 
                whileHover={{ scale: 1.1 }}
                className="w-10 h-10 bg-gray-700 rounded-2xl flex items-center justify-center"
              >
                <Hand className="w-5 h-5 text-blue-400" />
              </motion.div>
              <div>
                <h2 className="text-2xl font-bold text-white">Gripper Control</h2>
                <p className="text-sm text-gray-400">End-effector operations</p>
              </div>
            </div>

            <div className="space-y-6">
              {/* Quick Actions */}
              <div className="grid grid-cols-2 gap-4">
                <motion.button
                  onClick={openGripper}
                  disabled={!connected}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="flex items-center justify-center space-x-2 px-6 py-4 bg-blue-500 hover:bg-blue-600 text-white rounded-2xl font-semibold shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
                >
                  <Grip className="w-5 h-5" />
                  <span>Open</span>
                </motion.button>
                
                <motion.button
                  onClick={closeGripper}
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
              <div className="bg-gray-900/50 rounded-2xl p-6 border border-gray-700/50">
                <h3 className="text-lg font-semibold text-white mb-4">Precise Position</h3>
                <div className="flex items-center space-x-4">
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
                    onClick={setGripper}
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
        </div>

        {/* Connection Error Alert */}
        {connectionError && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6 }}
            className="mt-8 bg-red-900/20 border border-red-800 rounded-2xl p-6"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <AlertCircle className="w-6 h-6 text-red-400" />
                <div>
                  <h3 className="font-semibold text-red-400">Connection Error</h3>
                  <p className="text-red-300">{connectionError}</p>
                  <p className="text-sm text-red-400 mt-1">
                    Please ensure the backend server is running to control the robotic arm.
                  </p>
                </div>
              </div>
              <motion.button
                onClick={connectToSocket}
                disabled={reconnecting}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white rounded-lg font-semibold transition-colors duration-200 disabled:cursor-not-allowed"
              >
                <motion.div
                  animate={reconnecting ? { rotate: 360 } : {}}
                  transition={{ duration: 1, repeat: reconnecting ? Infinity : 0, ease: "linear" }}
                >
                  <RefreshCw className="w-4 h-4" />
                </motion.div>
                <span>{reconnecting ? 'Reconnecting...' : 'Retry Connection'}</span>
              </motion.button>
            </div>
          </motion.div>
        )}

        {/* Status Alert for Disconnection */}
        {!connected && !connectionError && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6 }}
            className="mt-8 bg-yellow-900/20 border border-yellow-800 rounded-2xl p-6"
          >
            <div className="flex items-center space-x-3">
              <AlertCircle className="w-6 h-6 text-yellow-400" />
              <div>
                <h3 className="font-semibold text-yellow-400">Connection Required</h3>
                <p className="text-yellow-300">
                  Attempting to connect to backend server...
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </section>
  );
}
