import { useState, useCallback, useEffect } from "react";
import { AlertCircle, RefreshCw } from 'lucide-react';
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

  const { status: connectionStatus, reconnect } = useSocketConnection('http://localhost:5000', {
    registerHandlers: useCallback((socket: Socket) => {
      const handleStatus = (data: { msg: string }) => {
        setMsg(data.msg);
      };

      const handleTelemetry = (data: any) => {
        setRobotState(data);
        if (data.q && data.q.length > 0) {
          // Convert radians to degrees for display
          const jointsDegrees = data.q.map((j: number) => (j * 180 / Math.PI).toFixed(2).toString());
          setJointInputs(jointsDegrees);
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
            onSolveIK={sendIK}
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
