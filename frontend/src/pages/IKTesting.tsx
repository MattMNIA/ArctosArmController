import React, { Suspense, useState, useCallback, useEffect, useRef } from "react";
import { Canvas, useLoader, useFrame } from "@react-three/fiber";
import { OrbitControls, Grid } from "@react-three/drei";
import URDFLoader from "urdf-loader";
import * as THREE from "three";
import { motion } from 'framer-motion';
import type { Socket } from 'socket.io-client';
import {
  ArrowUp, ArrowDown, ArrowLeft, ArrowRight,
  MoveVertical, RotateCcw, Play, Eye, RefreshCw,
  ChevronUp, ChevronDown, Crosshair, Home
} from 'lucide-react';
import { useSocketConnection } from '../hooks/useSocketConnection';
import { ConnectionIndicator } from '../components/ui/ConnectionIndicator';
import { AlertBanner } from '../components/ui/AlertBanner';
import { AnimatedButton } from '../components/ui/AnimatedButton';
import { PageHeader } from '../components/layout/PageHeader';
import { api, getSocketUrl } from '../api';

interface URDFProps {
  path: string;
  jointAngles: number[];
  previewAngles?: number[] | null;
  showPreview: boolean;
  gripperPosition?: number;
}

interface TelemetryData {
  state: string;
  q: number[];
  error: number[];
  limits: any[];
  gripper_position?: number;
}

interface FKResult {
  position: number[];
  orientation: number[];
  euler: number[];
}

interface IKResult {
  joints: number[];
  success: boolean;
  error: number | string;
}

// URDF Model component with preview support
const URDFModel: React.FC<URDFProps> = ({ path, jointAngles, previewAngles, showPreview, gripperPosition = 0 }) => {
  const urdf = useLoader(
    URDFLoader as any,
    path,
    (loader: URDFLoader) => {
      loader.packages = {
        "": "/models/meshes/",
      };
      loader.fetchOptions = {
        mode: "cors",
      };
    }
  );

  const [currentAngles, setCurrentAngles] = useState(jointAngles);
  const [targetAngles, setTargetAngles] = useState(jointAngles);

  useEffect(() => {
    // When showing preview, interpolate to preview angles; otherwise use live angles
    setTargetAngles(showPreview && previewAngles ? previewAngles : jointAngles);
  }, [jointAngles, previewAngles, showPreview]);

  useFrame(() => {
    setCurrentAngles(prev =>
      prev.map((current, i) =>
        THREE.MathUtils.lerp(current, targetAngles[i], 0.08)
      )
    );
  });

  React.useEffect(() => {
    if (urdf && currentAngles.length >= 6) {
      try {
        const jointNames = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6'];
        jointNames.forEach((jointName, index) => {
          if (urdf.joints && urdf.joints[jointName]) {
            urdf.joints[jointName].setJointValue(currentAngles[index] || 0);
          }
        });

        const jawPosition = (1 - gripperPosition) * 0.015;
        if (urdf.joints && urdf.joints['jaw1']) {
          urdf.joints['jaw1'].setJointValue(jawPosition);
        }
        if (urdf.joints && urdf.joints['jaw2']) {
          urdf.joints['jaw2'].setJointValue(jawPosition);
        }
      } catch (error) {
        console.error('Error setting joint values:', error);
      }
    }
  }, [urdf, currentAngles, gripperPosition]);

  if (!urdf) return null;

  urdf.rotation.x = -Math.PI / 2;

  urdf.traverse((c: THREE.Object3D) => {
    if ((c as THREE.Mesh).isMesh) {
      const mesh = c as THREE.Mesh;
      mesh.castShadow = true;
      mesh.receiveShadow = true;

      // Apply preview styling when in preview mode
      if (showPreview && previewAngles) {
        if (mesh.material) {
          const mat = mesh.material as THREE.MeshStandardMaterial;
          if (!mat.userData.originalColor) {
            mat.userData.originalColor = mat.color.clone();
          }
          mat.color.setHex(0x4488ff);
          mat.transparent = true;
          mat.opacity = 0.8;
        }
      } else {
        if (mesh.material) {
          const mat = mesh.material as THREE.MeshStandardMaterial;
          if (mat.userData.originalColor) {
            mat.color.copy(mat.userData.originalColor);
            mat.transparent = false;
            mat.opacity = 1;
          }
        }
      }
    }
  });

  return <primitive object={urdf} />;
};

// Movement command definitions
// Y axis = forward/back, X axis = left/right, Z axis = up/down
const MOVEMENT_COMMANDS = {
  forward: { label: 'Push Forward', icon: ArrowUp, delta: [0, 0.05, 0], description: '+Y axis' },
  backward: { label: 'Pull Back', icon: ArrowDown, delta: [0, -0.05, 0], description: '-Y axis' },
  left: { label: 'Move Left', icon: ArrowLeft, delta: [-0.05, 0, 0], description: '-X axis' },
  right: { label: 'Move Right', icon: ArrowRight, delta: [0.05, 0, 0], description: '+X axis' },
  up: { label: 'Move Up', icon: ChevronUp, delta: [0, 0, 0.05], description: '+Z axis' },
  down: { label: 'Move Down', icon: ChevronDown, delta: [0, 0, -0.05], description: '-Z axis' },
};

export default function IKTesting() {
  // State
  const [telemetry, setTelemetry] = useState<TelemetryData | null>(null);
  const [currentPose, setCurrentPose] = useState<FKResult | null>(null);
  const [previewJoints, setPreviewJoints] = useState<number[] | null>(null);
  const [previewPose, setPreviewPose] = useState<FKResult | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stepSize, setStepSize] = useState(0.05); // meters
  const [lastCommand, setLastCommand] = useState<string | null>(null);

  // Custom position inputs
  const [customPosition, setCustomPosition] = useState({ x: '0.3', y: '0.0', z: '0.3' });
  const [customOrientation, setCustomOrientation] = useState({ roll: '0', pitch: '0', yaw: '0' });

  // Socket connection
  const handleTelemetry = useCallback((data: TelemetryData) => {
    setTelemetry(data);
  }, []);

  const { status: connectionStatus } = useSocketConnection(getSocketUrl(), {
    registerHandlers: useCallback((socket: Socket) => {
      socket.on('telemetry', handleTelemetry);
      return () => socket.off('telemetry', handleTelemetry);
    }, [handleTelemetry]),
  });

  const { connected } = connectionStatus;
  const jointAngles = telemetry?.q || [0, 0, 0, 0, 0, 0];

  // Fetch current FK pose when telemetry updates
  useEffect(() => {
    if (!connected || !telemetry?.q) return;

    const fetchCurrentPose = async () => {
      try {
        const result = await api.post<FKResult>('/api/ik/fk', {
          joints: telemetry.q,
        });
        setCurrentPose(result);
      } catch (err) {
        console.error('Failed to get current pose:', err);
      }
    };

    fetchCurrentPose();
  }, [connected, telemetry?.q]);

  // Compute IK for a target pose
  const computeIK = async (targetPose: { position: number[]; euler?: number[] }) => {
    setLoading(true);
    setError(null);

    try {
      const result = await api.post<IKResult>('/api/ik/solve', {
        pose: targetPose,
        seed: telemetry?.q || [],
      });

      if (!result.success) {
        throw new Error(typeof result.error === 'string' ? result.error : 'IK solve failed');
      }

      // Get the FK for preview
      const fkResult = await api.post<FKResult>('/api/ik/fk', {
        joints: result.joints,
      });

      setPreviewJoints(result.joints);
      setPreviewPose(fkResult);
      setShowPreview(true);

      return result.joints;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to compute IK';
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  };

  // Handle relative movement commands (incremental - accumulates from preview if active)
  const handleMovementCommand = async (command: keyof typeof MOVEMENT_COMMANDS) => {
    // Use preview pose if in preview mode, otherwise use current pose
    const basePose = showPreview && previewPose ? previewPose : currentPose;

    if (!basePose) {
      setError('No current pose available. Make sure the arm is connected.');
      return;
    }

    const cmd = MOVEMENT_COMMANDS[command];
    const scaledDelta = cmd.delta.map(d => d * (stepSize / 0.05)); // Scale by step size

    const targetPosition = [
      basePose.position[0] + scaledDelta[0],
      basePose.position[1] + scaledDelta[1],
      basePose.position[2] + scaledDelta[2],
    ];

    // Use the base pose's orientation to maintain consistency
    const baseEuler = basePose.euler || currentPose?.euler || [0, 0, 0];

    setLastCommand(cmd.label);
    await computeIK({
      position: targetPosition,
      euler: baseEuler,
    });
  };

  // Handle custom position
  const handleCustomPosition = async () => {
    const position = [
      parseFloat(customPosition.x) || 0,
      parseFloat(customPosition.y) || 0,
      parseFloat(customPosition.z) || 0,
    ];
    const euler = [
      parseFloat(customOrientation.roll) || 0,
      parseFloat(customOrientation.pitch) || 0,
      parseFloat(customOrientation.yaw) || 0,
    ];

    setLastCommand('Custom Position');
    await computeIK({ position, euler });
  };

  // Execute the previewed move
  const executeMove = async () => {
    if (!previewJoints) return;

    setLoading(true);
    setError(null);

    try {
      await api.post('/api/execute/joints', {
        q: previewJoints,
      });
      setShowPreview(false);
      setPreviewJoints(null);
      setPreviewPose(null);
      setLastCommand(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to execute move';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  // Cancel preview
  const cancelPreview = () => {
    setShowPreview(false);
    setPreviewJoints(null);
    setPreviewPose(null);
    setLastCommand(null);
  };

  // Home position (X: 0.2mm, Y: -316.8mm, Z: 570.3mm)
  const goHome = async () => {
    setLastCommand('Home Position');
    await computeIK({
      position: [0.0002, -0.3168, 0.5703],
      euler: [0, 0, 0],
    });
  };

  // Update custom position from current pose
  const syncFromCurrent = () => {
    if (currentPose) {
      setCustomPosition({
        x: currentPose.position[0].toFixed(3),
        y: currentPose.position[1].toFixed(3),
        z: currentPose.position[2].toFixed(3),
      });
      setCustomOrientation({
        roll: currentPose.euler[0].toFixed(3),
        pitch: currentPose.euler[1].toFixed(3),
        yaw: currentPose.euler[2].toFixed(3),
      });
    }
  };

  return (
    <section className="py-8 min-h-screen">
      <div className="max-w-7xl mx-auto px-6">
        <PageHeader
          title="IK Testing & Visualization"
          description="Test inverse kinematics commands and preview movements before execution"
          centered
          statusSlot={
            <ConnectionIndicator
              connected={connected}
              connectedLabel="Connected"
              disconnectedLabel="Disconnected"
            />
          }
        />

        {error && (
          <AlertBanner
            variant="error"
            title="Error"
            message={error}
            action={{ label: 'Dismiss', onClick: () => setError(null) }}
            className="mb-6"
          />
        )}

        <div className="grid lg:grid-cols-3 gap-6">
          {/* 3D Visualization */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="lg:col-span-2 bg-gray-800 rounded-3xl shadow-lg border border-gray-700/50 overflow-hidden"
          >
            <div className="relative h-[500px]">
              {/* Preview indicator */}
              {showPreview && (
                <div className="absolute top-4 left-4 z-10 bg-blue-600/90 backdrop-blur-sm rounded-lg px-3 py-2 flex items-center gap-2">
                  <Eye className="w-4 h-4" />
                  <span className="text-sm font-medium">Preview Mode</span>
                  {lastCommand && <span className="text-xs opacity-75">({lastCommand})</span>}
                </div>
              )}

              {/* Pose info */}
              <div className="absolute top-4 right-4 z-10 bg-gray-800/90 backdrop-blur-sm rounded-lg p-3 text-xs">
                <div className="font-semibold mb-2 text-gray-300">
                  {showPreview ? 'Preview Pose' : 'Current Pose'}
                </div>
                {(showPreview ? previewPose : currentPose) ? (
                  <div className="space-y-1 text-gray-400">
                    <div>X: {((showPreview ? previewPose : currentPose)!.position[0] * 1000).toFixed(1)} mm</div>
                    <div>Y: {((showPreview ? previewPose : currentPose)!.position[1] * 1000).toFixed(1)} mm</div>
                    <div>Z: {((showPreview ? previewPose : currentPose)!.position[2] * 1000).toFixed(1)} mm</div>
                  </div>
                ) : (
                  <div className="text-gray-500">No data</div>
                )}
              </div>

              <Canvas
                shadows
                camera={{ position: [0.8, 0.6, 0.8], fov: 50 }}
                style={{ background: "#1a1a2e" }}
              >
                <ambientLight intensity={0.4} />
                <directionalLight
                  position={[5, 5, 5]}
                  intensity={1}
                  castShadow
                  shadow-mapSize-width={2048}
                  shadow-mapSize-height={2048}
                />
                <mesh receiveShadow rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
                  <planeGeometry args={[10, 10]} />
                  <meshStandardMaterial color="#2a2a3e" />
                </mesh>
                <Grid
                  cellSize={0.1}
                  sectionSize={0.5}
                  infiniteGrid={false}
                  position={[0, 0.001, 0]}
                  args={[2, 2]}
                />
                <Suspense fallback={null}>
                  <URDFModel
                    path="/models/urdf/arctos_urdf.urdf"
                    jointAngles={jointAngles}
                    previewAngles={previewJoints}
                    showPreview={showPreview}
                    gripperPosition={telemetry?.gripper_position}
                  />
                </Suspense>
                <OrbitControls />
              </Canvas>
            </div>

            {/* Execute/Cancel buttons */}
            {showPreview && (
              <div className="p-4 border-t border-gray-700 flex gap-3 justify-center">
                <AnimatedButton
                  variant="success"
                  size="lg"
                  onClick={executeMove}
                  disabled={loading}
                  leftIcon={<Play className="w-5 h-5" />}
                >
                  {loading ? 'Executing...' : 'Execute Move'}
                </AnimatedButton>
                <AnimatedButton
                  variant="secondary"
                  size="lg"
                  onClick={cancelPreview}
                  disabled={loading}
                  leftIcon={<RotateCcw className="w-5 h-5" />}
                >
                  Cancel
                </AnimatedButton>
              </div>
            )}
          </motion.div>

          {/* Controls Panel */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="space-y-6"
          >
            {/* Quick Movement Commands */}
            <div className="bg-gray-800 rounded-3xl shadow-lg border border-gray-700/50 p-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <MoveVertical className="w-5 h-5 text-blue-400" />
                Cartesian Movement
              </h3>

              {/* Step size control */}
              <div className="mb-4">
                <label className="block text-sm text-gray-400 mb-2">Step Size</label>
                <div className="flex gap-2">
                  {[0.01, 0.025, 0.05, 0.1].map((size) => (
                    <button
                      key={size}
                      onClick={() => setStepSize(size)}
                      className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                        stepSize === size
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                      }`}
                    >
                      {size * 1000}mm
                    </button>
                  ))}
                </div>
              </div>

              {/* Movement grid */}
              <div className="grid grid-cols-3 gap-2 mb-4">
                {/* Top row - empty, forward, empty */}
                <div />
                <button
                  onClick={() => handleMovementCommand('forward')}
                  disabled={loading || !connected}
                  className="p-3 rounded-xl bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex flex-col items-center gap-1"
                  title={MOVEMENT_COMMANDS.forward.description}
                >
                  <ArrowUp className="w-5 h-5" />
                  <span className="text-xs">Forward</span>
                </button>
                <div />

                {/* Middle row - left, home, right */}
                <button
                  onClick={() => handleMovementCommand('left')}
                  disabled={loading || !connected}
                  className="p-3 rounded-xl bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex flex-col items-center gap-1"
                  title={MOVEMENT_COMMANDS.left.description}
                >
                  <ArrowLeft className="w-5 h-5" />
                  <span className="text-xs">Left</span>
                </button>
                <button
                  onClick={goHome}
                  disabled={loading || !connected}
                  className="p-3 rounded-xl bg-blue-600/30 hover:bg-blue-600/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex flex-col items-center gap-1"
                  title="Go to home position"
                >
                  <Home className="w-5 h-5" />
                  <span className="text-xs">Home</span>
                </button>
                <button
                  onClick={() => handleMovementCommand('right')}
                  disabled={loading || !connected}
                  className="p-3 rounded-xl bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex flex-col items-center gap-1"
                  title={MOVEMENT_COMMANDS.right.description}
                >
                  <ArrowRight className="w-5 h-5" />
                  <span className="text-xs">Right</span>
                </button>

                {/* Bottom row - empty, backward, empty */}
                <div />
                <button
                  onClick={() => handleMovementCommand('backward')}
                  disabled={loading || !connected}
                  className="p-3 rounded-xl bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex flex-col items-center gap-1"
                  title={MOVEMENT_COMMANDS.backward.description}
                >
                  <ArrowDown className="w-5 h-5" />
                  <span className="text-xs">Back</span>
                </button>
                <div />
              </div>

              {/* Up/Down buttons */}
              <div className="flex gap-2">
                <button
                  onClick={() => handleMovementCommand('up')}
                  disabled={loading || !connected}
                  className="flex-1 p-3 rounded-xl bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                  title={MOVEMENT_COMMANDS.up.description}
                >
                  <ChevronUp className="w-5 h-5" />
                  <span className="text-sm">Up</span>
                </button>
                <button
                  onClick={() => handleMovementCommand('down')}
                  disabled={loading || !connected}
                  className="flex-1 p-3 rounded-xl bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                  title={MOVEMENT_COMMANDS.down.description}
                >
                  <ChevronDown className="w-5 h-5" />
                  <span className="text-sm">Down</span>
                </button>
              </div>
            </div>

            {/* Custom Position */}
            <div className="bg-gray-800 rounded-3xl shadow-lg border border-gray-700/50 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                  <Crosshair className="w-5 h-5 text-green-400" />
                  Custom Position
                </h3>
                <button
                  onClick={syncFromCurrent}
                  disabled={!currentPose}
                  className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50"
                  title="Copy current pose to inputs"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-2">
                  {(['x', 'y', 'z'] as const).map((axis) => (
                    <div key={axis}>
                      <label className="block text-xs text-gray-400 mb-1 uppercase">{axis} (m)</label>
                      <input
                        type="number"
                        step="0.01"
                        value={customPosition[axis]}
                        onChange={(e) => setCustomPosition({ ...customPosition, [axis]: e.target.value })}
                        className="w-full px-2 py-1.5 rounded-lg border border-gray-600 bg-gray-700 text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                    </div>
                  ))}
                </div>

                <div className="grid grid-cols-3 gap-2">
                  {(['roll', 'pitch', 'yaw'] as const).map((angle) => (
                    <div key={angle}>
                      <label className="block text-xs text-gray-400 mb-1 capitalize">{angle} (rad)</label>
                      <input
                        type="number"
                        step="0.1"
                        value={customOrientation[angle]}
                        onChange={(e) => setCustomOrientation({ ...customOrientation, [angle]: e.target.value })}
                        className="w-full px-2 py-1.5 rounded-lg border border-gray-600 bg-gray-700 text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                    </div>
                  ))}
                </div>

                <AnimatedButton
                  variant="primary"
                  size="md"
                  onClick={handleCustomPosition}
                  disabled={loading || !connected}
                  className="w-full"
                  leftIcon={<Eye className="w-4 h-4" />}
                >
                  {loading ? 'Computing...' : 'Preview Position'}
                </AnimatedButton>
              </div>
            </div>

            {/* Current Joint Angles */}
            <div className="bg-gray-800 rounded-3xl shadow-lg border border-gray-700/50 p-6">
              <h3 className="text-lg font-semibold mb-4">Joint Angles</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                {jointAngles.map((angle, index) => (
                  <div key={index} className="flex justify-between px-2 py-1 bg-gray-700/50 rounded">
                    <span className="text-gray-400">J{index + 1}:</span>
                    <span className="font-mono">{(angle * 180 / Math.PI).toFixed(1)}°</span>
                  </div>
                ))}
              </div>
              {showPreview && previewJoints && (
                <>
                  <div className="mt-4 pt-4 border-t border-gray-700">
                    <div className="text-sm text-blue-400 mb-2">Preview Joints</div>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      {previewJoints.map((angle, index) => (
                        <div key={index} className="flex justify-between px-2 py-1 bg-blue-900/30 rounded">
                          <span className="text-blue-300">J{index + 1}:</span>
                          <span className="font-mono">{(angle * 180 / Math.PI).toFixed(1)}°</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
