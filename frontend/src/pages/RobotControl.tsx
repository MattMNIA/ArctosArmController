import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { motion } from 'framer-motion';
import { AlertCircle, RefreshCw, Calculator, Play, StopCircle } from 'lucide-react';
import type { Socket } from 'socket.io-client';
import JointControl from '../components/JointControl';
import GripperControl from '../components/GripperControl';
import { AnimatedButton } from '../components/ui/AnimatedButton';
import { ConnectionIndicator } from '../components/ui/ConnectionIndicator';
import { AlertBanner } from '../components/ui/AlertBanner';
import { PageHeader } from '../components/layout/PageHeader';
import { useSocketConnection } from '../hooks/useSocketConnection';

type TeleopModeOptionSchema = {
  type: 'string' | 'boolean';
  label: string;
  default?: any;
  placeholder?: string;
  options?: string[];
};

type TeleopModeDefinition = {
  id: string;
  label: string;
  description: string;
  supportsOptions: boolean;
  type?: string;
  options?: Record<string, TeleopModeOptionSchema>;
};

type TeleopStateSnapshot = {
  primaryMode: string | null;
  running: boolean;
  paused: boolean;
  lastError: string | null;
};

export default function RobotControl() {
  const [msg, setMsg] = useState("Connecting...");
  const [jointInputs, setJointInputs] = useState<string[]>(['0','0','0','0','0','0']);
  const [gripperInput, setGripperInput] = useState<string>('0.0');
  const [loading, setLoading] = useState(false);
  const [fkResult, setFkResult] = useState<{ position: number[]; orientation: number[] } | null>(null);
  const inputsInitializedRef = useRef(false);
  const [ikPosition, setIkPosition] = useState<string[]>(['0.3', '0.1', '0.2']);
  const [ikOrientation, setIkOrientation] = useState<string[]>(['0', '0', '0', '1']);
  const [useEulerAngles, setUseEulerAngles] = useState(false);
  const [solvedJoints, setSolvedJoints] = useState<number[] | null>(null);
  const [teleopModes, setTeleopModes] = useState<TeleopModeDefinition[]>([]);
  const [teleopState, setTeleopState] = useState<TeleopStateSnapshot>({ primaryMode: null, running: false, paused: false, lastError: null });
  const [selectedTeleopMode, setSelectedTeleopMode] = useState<string>('');
  const [teleopOptions, setTeleopOptions] = useState<Record<string, any>>({});
  const [teleopBusy, setTeleopBusy] = useState(false);
  const [teleopError, setTeleopError] = useState<string | null>(null);
  const teleopOptionsModeRef = useRef<string | null>(null);

  const buildDefaultOptionsForMode = useCallback(
    (modeId: string) => {
      const mode = teleopModes.find((entry) => entry.id === modeId);
      if (!mode || !mode.options) {
        return {};
      }
      const defaults: Record<string, any> = {};
      Object.entries(mode.options).forEach(([key, schema]) => {
        if (schema.type === 'boolean') {
          defaults[key] = schema.default ?? false;
        } else if (schema.options) {
          defaults[key] = schema.default ?? schema.options[0];
        } else {
          defaults[key] = schema.default ?? '';
        }
      });
      return defaults;
    },
    [teleopModes]
  );

  const selectedModeDefinition = useMemo(
    () => teleopModes.find((mode) => mode.id === selectedTeleopMode),
    [teleopModes, selectedTeleopMode]
  );

  const activeModeLabel = useMemo(() => {
    if (!teleopState.primaryMode) {
      return 'None';
    }
    const active = teleopModes.find((mode) => mode.id === teleopState.primaryMode);
    return active?.label ?? teleopState.primaryMode;
  }, [teleopModes, teleopState.primaryMode]);

  const sanitizeTeleopOptions = useCallback((raw: Record<string, any>) => {
    const sanitized: Record<string, any> = {};
    Object.entries(raw).forEach(([key, value]) => {
      if (typeof value === 'string') {
        const trimmed = value.trim();
        if (trimmed !== '') {
          sanitized[key] = trimmed;
        }
      } else {
        sanitized[key] = value;
      }
    });
    return sanitized;
  }, []);

  const handleOptionChange = useCallback((key: string, value: string | boolean) => {
    setTeleopOptions((prev) => ({ ...prev, [key]: value }));
  }, []);

  const fetchTeleopModes = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:5000/api/teleop/modes');
      if (!res.ok) {
        throw new Error(`Request failed with status ${res.status}`);
      }
      const data = await res.json();
      const modes = Array.isArray(data.modes) ? data.modes : [];
      setTeleopModes(modes);
    } catch (error) {
      console.error('Failed to load teleop modes:', error);
      setTeleopError('Unable to load teleoperation modes from the backend.');
    }
  }, []);

  const fetchTeleopState = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:5000/api/teleop/state');
      if (!res.ok) {
        throw new Error(`Request failed with status ${res.status}`);
      }
      const data = await res.json();
      const state = data.state ?? data;
      setTeleopState({
        primaryMode: state.primaryMode ?? null,
        running: Boolean(state.running),
        paused: Boolean(state.paused),
        lastError: state.lastError ?? null,
      });
    } catch (error) {
      console.error('Failed to load teleop state:', error);
      setTeleopError((prev) => prev ?? 'Unable to load teleoperation state from the backend.');
    }
  }, []);

  const startTeleopMode = useCallback(async () => {
    if (!selectedTeleopMode) {
      return;
    }
    setTeleopBusy(true);
    setTeleopError(null);
    try {
      const optionsPayload = sanitizeTeleopOptions(teleopOptions);
      const res = await fetch('http://localhost:5000/api/teleop/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: selectedTeleopMode, options: optionsPayload }),
      });
      if (!res.ok) {
        const errorText = await res.text();
        let message = errorText || `Request failed with status ${res.status}`;
        try {
          const parsed = JSON.parse(errorText);
          if (parsed && typeof parsed === 'object' && 'error' in parsed) {
            message = String(parsed.error);
          }
        } catch (_) {
          // ignore JSON parsing error; fall back to text message
        }
        throw new Error(message);
      }
      const data = await res.json();
      const state = data.state ?? data;
      setTeleopState({
        primaryMode: state.primaryMode ?? null,
        running: Boolean(state.running),
        paused: Boolean(state.paused),
        lastError: state.lastError ?? null,
      });
      await fetchTeleopState();
    } catch (error) {
      console.error('Failed to start teleop mode:', error);
      const message = error instanceof Error ? error.message : 'Failed to start teleoperation mode.';
      setTeleopError(message);
    } finally {
      setTeleopBusy(false);
    }
  }, [fetchTeleopState, sanitizeTeleopOptions, selectedTeleopMode, teleopOptions]);

  const stopTeleopMode = useCallback(async () => {
    setTeleopBusy(true);
    setTeleopError(null);
    try {
      const res = await fetch('http://localhost:5000/api/teleop/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        const errorText = await res.text();
        let message = errorText || `Request failed with status ${res.status}`;
        try {
          const parsed = JSON.parse(errorText);
          if (parsed && typeof parsed === 'object' && 'error' in parsed) {
            message = String(parsed.error);
          }
        } catch (_) {
          // ignore JSON parsing error; fall back to text message
        }
        throw new Error(message);
      }
      const data = await res.json();
      const state = data.state ?? data;
      setTeleopState({
        primaryMode: state.primaryMode ?? null,
        running: Boolean(state.running),
        paused: Boolean(state.paused),
        lastError: state.lastError ?? null,
      });
      await fetchTeleopState();
    } catch (error) {
      console.error('Failed to stop teleop mode:', error);
      const message = error instanceof Error ? error.message : 'Failed to stop teleoperation mode.';
      setTeleopError(message);
    } finally {
      setTeleopBusy(false);
    }
  }, [fetchTeleopState]);

  useEffect(() => {
    fetchTeleopModes();
    fetchTeleopState();
  }, [fetchTeleopModes, fetchTeleopState]);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchTeleopState();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchTeleopState]);

  useEffect(() => {
    if (!teleopModes.length) {
      return;
    }
    setSelectedTeleopMode((prev) => {
      if (prev && teleopModes.some((mode) => mode.id === prev)) {
        return prev;
      }
      const active = teleopState.primaryMode && teleopModes.some((mode) => mode.id === teleopState.primaryMode)
        ? teleopState.primaryMode
        : teleopModes[0].id;
      return active ?? prev;
    });
  }, [teleopModes, teleopState.primaryMode]);

  useEffect(() => {
    if (!selectedTeleopMode) {
      return;
    }
    if (teleopOptionsModeRef.current === selectedTeleopMode) {
      return;
    }
    teleopOptionsModeRef.current = selectedTeleopMode;
    setTeleopOptions(buildDefaultOptionsForMode(selectedTeleopMode));
  }, [buildDefaultOptionsForMode, selectedTeleopMode]);

  const isSelectedModeRunning = teleopState.running && teleopState.primaryMode === selectedTeleopMode;
  const teleopStatusLabel = teleopState.running ? 'Active' : 'Idle';
  const startButtonLabel = teleopState.running
    ? (isSelectedModeRunning ? 'Restart Mode' : 'Switch Mode')
    : 'Start Mode';

  // Handle orientation format changes
  useEffect(() => {
    if (useEulerAngles && ikOrientation.length === 4) {
      // Switching to Euler: keep first 3 values (X, Y, Z from quaternion)
      setIkOrientation(ikOrientation.slice(1, 4));
    } else if (!useEulerAngles && ikOrientation.length === 3) {
      // Switching to Quaternion: prepend 1 (W) and keep the rest
      setIkOrientation(['1', ...ikOrientation]);
    }
  }, [useEulerAngles]);

  const { status: connectionStatus, reconnect } = useSocketConnection('http://localhost:5000', {
    registerHandlers: useCallback((socket: Socket) => {
      const handleStatus = (data: { msg: string }) => {
        setMsg(data.msg);
      };

      const handleTelemetry = (data: any) => {
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
      
      const pose: any = { position };
      if (useEulerAngles) {
        pose.euler = orientation;
      } else {
        pose.orientation = orientation;
      }
      
      const res = await fetch("http://localhost:5000/api/ik/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          pose, 
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

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="bg-gray-800 rounded-3xl shadow-lg border border-gray-700/50 p-6 w-full"
        >
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold">Teleoperation Modes</h2>
              <p className="text-sm text-gray-400 mt-1">
                Switch controllers on the fly without restarting the backend service.
              </p>
            </div>
            <div className="text-sm text-gray-300 space-y-1 md:text-right">
              <div>
                <span className="text-gray-400 mr-2">Status:</span>
                <span className={teleopState.running ? 'text-green-400 font-semibold' : 'text-yellow-300 font-semibold'}>
                  {teleopStatusLabel}
                </span>
              </div>
              <div>
                <span className="text-gray-400 mr-2">Primary mode:</span>
                <span className="font-semibold">{activeModeLabel}</span>
              </div>
              {teleopState.paused && (
                <div>
                  <span className="text-gray-400 mr-2">State:</span>
                  <span className="font-semibold text-orange-400">Paused</span>
                </div>
              )}
            </div>
          </div>

          {teleopError && (
            <div className="mt-4">
              <AlertBanner
                variant="error"
                title="Teleoperation Error"
                message={teleopError}
                action={{ label: 'Dismiss', onClick: () => setTeleopError(null) }}
              />
            </div>
          )}

          <div className="mt-6 grid gap-4 md:grid-cols-2 md:items-end">
            <div>
              <label className="block text-sm font-semibold text-gray-300 mb-2">Controller mode</label>
              <select
                value={selectedTeleopMode}
                onChange={(event) => setSelectedTeleopMode(event.target.value)}
                disabled={!teleopModes.length || teleopBusy}
                className="w-full px-3 py-2 rounded-lg border border-gray-600 bg-gray-700 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {teleopModes.filter(mode => mode.type !== 'gesture').map((mode) => (
                  <option key={mode.id} value={mode.id}>
                    {mode.label}
                  </option>
                ))}
              </select>
              {!teleopModes.length && (
                <p className="text-xs text-red-400 mt-2">No teleoperation modes available.</p>
              )}
              {selectedModeDefinition && (
                <p className="text-xs text-gray-500 mt-2">{selectedModeDefinition.description}</p>
              )}
            </div>
            <div className="flex gap-3 md:justify-end">
              <AnimatedButton
                variant="success"
                size="md"
                onClick={startTeleopMode}
                disabled={teleopBusy || !selectedTeleopMode}
                leftIcon={<Play className="w-4 h-4" />}
              >
                {teleopBusy ? 'Working...' : startButtonLabel}
              </AnimatedButton>
              <AnimatedButton
                variant="secondary"
                size="md"
                onClick={stopTeleopMode}
                disabled={teleopBusy || !teleopState.running}
                leftIcon={<StopCircle className="w-4 h-4" />}
              >
                {teleopBusy && teleopState.running ? 'Working...' : 'Stop Mode'}
              </AnimatedButton>
            </div>
          </div>

          {selectedModeDefinition?.supportsOptions && selectedModeDefinition.options && (
            <div className="mt-6 border-t border-gray-700/60 pt-6">
              <h3 className="text-sm font-semibold text-gray-300 mb-4">Mode options</h3>
              <div className="grid gap-4 md:grid-cols-2">
                {Object.entries(selectedModeDefinition.options).map(([key, option]) => (
                  option.type === 'boolean' ? (
                    <label
                      key={key}
                      className="flex items-center justify-between px-4 py-3 rounded-xl border border-gray-700/60 bg-gray-700/40"
                    >
                      <span className="text-sm text-gray-200">{option.label}</span>
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-gray-500 bg-gray-600 text-blue-500 focus:ring-blue-500"
                        checked={Boolean(teleopOptions[key])}
                        onChange={(event) => handleOptionChange(key, event.target.checked)}
                        disabled={teleopBusy}
                      />
                    </label>
                  ) : option.options ? (
                    <div key={key}>
                      <label className="block text-sm text-gray-200 mb-2">{option.label}</label>
                      <select
                        value={teleopOptions[key] ?? option.default ?? ''}
                        onChange={(event) => handleOptionChange(key, event.target.value)}
                        disabled={teleopBusy}
                        className="w-full px-3 py-2 rounded-lg border border-gray-600 bg-gray-700 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {option.options.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <div key={key}>
                      <label className="block text-sm text-gray-200 mb-2">{option.label}</label>
                      <input
                        type="text"
                        value={teleopOptions[key] ?? ''}
                        placeholder={option.placeholder ?? ''}
                        onChange={(event) => handleOptionChange(key, event.target.value)}
                        disabled={teleopBusy}
                        className="w-full px-3 py-2 rounded-lg border border-gray-600 bg-gray-700 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                  )
                ))}
              </div>
            </div>
          )}

          {/* Pause/Resume Controls for Object Centering */}
          {teleopState.primaryMode === 'object-centering' && (
            <div className="mt-6 border-t border-gray-700/60 pt-6">
              <h3 className="text-sm font-semibold text-gray-300 mb-4">Object Centering Control</h3>
              <div className="flex gap-3">
                <AnimatedButton
                  variant={teleopState.paused ? "success" : "secondary"}
                  size="md"
                  onClick={async () => {
                    setTeleopBusy(true);
                    try {
                      const endpoint = teleopState.paused ? 'resume' : 'pause';
                      const res = await fetch(`http://localhost:5000/api/teleop/${endpoint}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                      });
                      if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
                      const data = await res.json();
                      setTeleopState({
                        primaryMode: data.state.primaryMode ?? null,
                        running: Boolean(data.state.running),
                        paused: Boolean(data.state.paused),
                        lastError: data.state.lastError ?? null,
                      });
                    } catch (error) {
                      console.error(`Failed to ${teleopState.paused ? 'resume' : 'pause'}:`, error);
                      setTeleopError(`Failed to ${teleopState.paused ? 'resume' : 'pause'} object centering`);
                    } finally {
                      setTeleopBusy(false);
                    }
                  }}
                  disabled={teleopBusy}
                  leftIcon={teleopState.paused ? <Play className="w-4 h-4" /> : <StopCircle className="w-4 h-4" />}
                >
                  {teleopState.paused ? 'Resume Centering' : 'Pause Centering'}
                </AnimatedButton>
                <div className="text-sm text-gray-400 self-center">
                  {teleopState.paused ? 'Centering is paused' : 'Centering is active'}
                </div>
              </div>
            </div>
          )}

          {teleopState.lastError && (
            <p className="text-sm text-red-400 mt-6">Last error: {teleopState.lastError}</p>
          )}
        </motion.div>

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
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-gray-300">
                  Target Orientation {useEulerAngles ? '(Euler angles - radians)' : '(Quaternion)'}
                </h3>
                <label className="flex items-center space-x-2 text-sm">
                  <input
                    type="checkbox"
                    checked={useEulerAngles}
                    onChange={(e) => setUseEulerAngles(e.target.checked)}
                    className="rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500"
                  />
                  <span className="text-gray-400">Use Euler Angles</span>
                </label>
              </div>
              <div className="space-y-2">
                {(useEulerAngles ? ['Roll', 'Pitch', 'Yaw'] : ['W', 'X', 'Y', 'Z']).map((comp, index) => (
                  <div key={comp} className="flex items-center space-x-2">
                    <label className="text-sm text-gray-400 w-12">{comp}:</label>
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
