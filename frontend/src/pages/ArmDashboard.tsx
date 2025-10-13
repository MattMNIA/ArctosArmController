import { useCallback, useMemo, useState } from "react";
import { RefreshCw, Activity } from 'lucide-react';
import type { Socket } from 'socket.io-client';
import MotorCard from '../components/MotorCard';
import JointControl from '../components/JointControl';
import GripperControl from '../components/GripperControl';
import { useSocketConnection } from '../hooks/useSocketConnection';
import { ConnectionIndicator } from '../components/ui/ConnectionIndicator';
import { AlertBanner } from '../components/ui/AlertBanner';
import { LoadingState } from '../components/ui/LoadingState';
import { MotorCardPlaceholder } from '../components/MotorCardPlaceholder';

interface MotorStatus {
  state: string;
  q: number[];
  error: any[];
  limits: any[];
}

export default function ArmDashboard() {
  const [status, setStatus] = useState<MotorStatus | null>(null);
  const [initialTelemetryReceived, setInitialTelemetryReceived] = useState(false);
  const [jointInputs, setJointInputs] = useState<string[]>(['0','0','0','0','0','0']);
  const [jointLoading, setJointLoading] = useState(false);
  const [gripperInput, setGripperInput] = useState<string>('0.5');
  const handleTelemetry = useCallback((data: MotorStatus) => {
    setStatus(data);
    setInitialTelemetryReceived(true);
  }, []);

  const { status: connectionStatus, reconnect } = useSocketConnection('http://localhost:5000', {
    registerHandlers: useCallback((socket: Socket) => {
      socket.on('telemetry', handleTelemetry);
      return () => socket.off('telemetry', handleTelemetry);
    }, [handleTelemetry]),
    onDisconnect: () => {
      setInitialTelemetryReceived(false);
    },
    onConnectError: (_error) => {
      void _error;
      return 'Failed to connect to backend server. Please ensure the backend is running.';
    },
  });

  const { connected, loading: connecting, reconnecting, error } = connectionStatus;

  const loadingMessage = connecting
    ? 'Connecting to motors...'
    : 'Waiting for telemetry...';

  const showLoading = connecting || (connected && !initialTelemetryReceived);

  const sendIK = async () => {
    setJointLoading(true);
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
      setJointLoading(false);
    }
  };

  const executeMove = async () => {
    setJointLoading(true);
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
      setJointLoading(false);
    }
  };

  const openGripper = async () => {
    try {
      await fetch("http://localhost:5000/api/execute/gripper", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position: 0.0 })
      });
    } catch (error) {
      console.error("Open gripper failed:", error);
    }
  };

  const closeGripper = async () => {
    try {
      await fetch("http://localhost:5000/api/execute/gripper", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position: 1.0 })
      });
    } catch (error) {
      console.error("Close gripper failed:", error);
    }
  };

  const setGripperPosition = async () => {
    try {
      const position = parseFloat(gripperInput) || 0.5;
      await fetch("http://localhost:5000/api/execute/gripper", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position })
      });
    } catch (error) {
      console.error("Set gripper position failed:", error);
    }
  };

  const isEnabled = status ? ['RUNNING', 'EXECUTING'].includes(status.state) : false;
  const limits = useMemo(() => status?.limits ?? [], [status]);
  const errors = useMemo(() => status?.error ?? [], [status]);

  return (
    <section className="py-4 min-h-screen">
      <div className="w-full px-4">
        {/* Compact Header with Connection Status */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-4">
            <Activity className="w-6 h-6 text-blue-400" />
            <div>
              <h3 className="font-semibold text-white">System State</h3>
              <p className="text-sm text-gray-400">
                {status ? status.state : 'Connecting...'}
              </p>
            </div>
          </div>

          {/* Connection Status */}
          <ConnectionIndicator connected={connected} />
        </div>

        {/* Loading State */}
        {showLoading && <LoadingState message={loadingMessage} className="py-12" />}

        {/* Error State */}
        {error && (
          <AlertBanner
            variant="error"
            title="Connection Error"
            message={error}
            action={{
              label: reconnecting ? 'Reconnecting...' : 'Retry',
              onClick: reconnect,
              icon: <RefreshCw className="w-4 h-4" />,
              loading: reconnecting,
            }}
            className="mb-6"
          />
        )}

        {!connected && !error && !connecting && (
          <AlertBanner
            variant="warning"
            title="Connection Required"
            message="Attempting to connect to backend server..."
            className="mb-6"
          />
        )}

        {/* Main Content - Single Column Layout */}
        <div className="space-y-6">
          {/* Motor Status Cards - 1x6 Grid */}
          <div>
            {connected && status && status.q ? (
              <div className="grid grid-cols-6 gap-4">
                {status.q.map((position, idx) => {
                  const limit = limits[idx] || [false, false];
                  const topLimitHit = limit[0] || false;
                  const bottomLimitHit = limit[1] || false;
                  const encoderError = errors[idx] || 0;

                  return (
                    <MotorCard
                      key={idx}
                      motorIndex={idx}
                      position={position}
                      isEnabled={isEnabled}
                      topLimitHit={topLimitHit}
                      bottomLimitHit={bottomLimitHit}
                      encoderError={encoderError}
                    />
                  );
                })}
              </div>
            ) : !showLoading && (
              // Show placeholder cards when disconnected
              <div className="grid grid-cols-6 gap-4">
                {Array.from({ length: 6 }).map((_, idx) => (
                  <MotorCardPlaceholder key={idx} index={idx} dense />
                ))}
              </div>
            )}
          </div>

          {/* Control Panel - Two Column Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Joint Control */}
            <div className="h-full">
              <JointControl
                jointInputs={jointInputs}
                setJointInputs={setJointInputs}
                connected={connected}
                loading={jointLoading}
                onSolveIK={sendIK}
                onExecuteMove={executeMove}
              />
            </div>

            {/* Gripper Control */}
            <div className="h-full">
              <GripperControl
                gripperInput={gripperInput}
                setGripperInput={setGripperInput}
                connected={connected}
                onOpenGripper={openGripper}
                onCloseGripper={closeGripper}
                onSetGripper={setGripperPosition}
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}