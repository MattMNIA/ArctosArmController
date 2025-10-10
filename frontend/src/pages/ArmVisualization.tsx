import React, { Suspense, useEffect, useState, useCallback } from "react";
import { Canvas, useLoader, useFrame } from "@react-three/fiber";
import { OrbitControls, Grid } from "@react-three/drei";
import URDFLoader from "urdf-loader";
import * as THREE from "three";
import type { Socket } from 'socket.io-client';
import { useSocketConnection } from '../hooks/useSocketConnection';
import { ConnectionIndicator } from '../components/ui/ConnectionIndicator';
import { AlertBanner } from '../components/ui/AlertBanner';
import { LoadingState } from '../components/ui/LoadingState';

interface URDFProps {
  path: string;
  jointAngles: number[];
  gripperPosition?: number;
}

interface TelemetryData {
  state: string;
  q: number[];
  error: number[];
  limits: any[];
  gripper_position?: number;
}

const URDFModel: React.FC<URDFProps> = ({ path, jointAngles, gripperPosition = 0 }) => {
  const urdf = useLoader(
    URDFLoader as any,
    path,
    (loader: URDFLoader) => {
      loader.packages = {
        "": "/models/meshes/", // Maps package:// to /public/models/meshes/
      };
      loader.fetchOptions = {
        mode: "cors",
      };
    }
  );

  const [currentAngles, setCurrentAngles] = useState(jointAngles);
  const [targetAngles, setTargetAngles] = useState(jointAngles);

  // Update target angles when jointAngles prop changes
  useEffect(() => {
    setTargetAngles(jointAngles);
  }, [jointAngles]);

  // Smooth interpolation using useFrame
  useFrame(() => {
    setCurrentAngles(prev =>
      prev.map((current, i) =>
        THREE.MathUtils.lerp(current, targetAngles[i], 0.05) // Adjust 0.05 for smoothing speed
      )
    );
  });

  // Apply current joint angles when they change
  React.useEffect(() => {
    if (urdf && currentAngles.length >= 6) {
      try {
        // Set joint values for the 6 revolute joints
        const jointNames = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6'];

        jointNames.forEach((jointName, index) => {
          if (urdf.joints && urdf.joints[jointName]) {
            urdf.joints[jointName].setJointValue(currentAngles[index] || 0);
          }
        });

        // Set gripper jaw positions based on gripper position (0.0 = open, 1.0 = closed)
        const jawPosition = (1 - gripperPosition) * 0.015; // URDF limit is 0.015
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

// Apply a rotation correction
urdf.rotation.x = -Math.PI / 2; // rotate -90 degrees around X
// urdf.rotation.z = Math.PI; // optional flip if needed


  // Enable shadows if desired
  urdf.traverse((c: THREE.Object3D) => {
    if ((c as THREE.Mesh).isMesh) {
      (c as THREE.Mesh).castShadow = true;
      (c as THREE.Mesh).receiveShadow = true;
    }
  });

  return <primitive object={urdf} />;
};

const RoboticArmViewer: React.FC = () => {
  const [telemetry, setTelemetry] = useState<TelemetryData | null>(null);
  const [initialTelemetryReceived, setInitialTelemetryReceived] = useState(false);

  const handleTelemetry = useCallback((data: TelemetryData) => {
    setTelemetry(data);
    setInitialTelemetryReceived(true);
  }, []);

  const { status: connectionStatus } = useSocketConnection('http://localhost:5000', {
    registerHandlers: useCallback((socket: Socket) => {
      socket.on('telemetry', handleTelemetry);
      return () => socket.off('telemetry', handleTelemetry);
    }, [handleTelemetry]),
    onDisconnect: () => {
      setInitialTelemetryReceived(false);
    },
    onConnectError: (error) => {
      console.error('WebSocket connection error:', error);
      return 'Failed to connect to backend server. Please ensure the backend is running.';
    },
  });

  const { connected, loading: connecting, error } = connectionStatus;

  // Default joint angles if no telemetry received
  const jointAngles = telemetry?.q || [0, 0, 0, 0, 0, 0];
  const showLoading = connecting || (connected && !initialTelemetryReceived);

  return (
    <div className="relative w-full h-screen bg-gray-900">
      {/* Connection Status Indicator */}
      <div className="absolute top-4 left-4 z-10 flex items-center space-x-2 bg-gray-800/80 backdrop-blur-sm rounded-lg px-3 py-2">
        <ConnectionIndicator connected={connected} />
      </div>

      {showLoading && (
        <div className="absolute top-16 left-1/2 z-10 w-full max-w-xs -translate-x-1/2">
          <LoadingState message={connecting ? 'Connecting to simulation...' : 'Waiting for telemetry...'} className="py-4" />
        </div>
      )}

      {error && (
        <div className="absolute top-4 left-1/2 z-10 w-full max-w-lg -translate-x-1/2">
          <AlertBanner
            variant="error"
            title="Connection Error"
            message={error}
          />
        </div>
      )}

      {/* Joint Angles Display */}
      <div className="absolute top-4 right-4 z-10 bg-gray-800/80 backdrop-blur-sm rounded-lg p-3 max-w-xs">
        <h3 className="text-sm font-semibold text-white mb-2">Joint Angles</h3>
        <div className="grid grid-cols-2 gap-2 text-xs">
          {jointAngles.map((angle, index) => (
            <div key={index} className="text-gray-300">
              J{index + 1}: {(angle * 180 / Math.PI).toFixed(1)}°
            </div>
          ))}
        </div>
      </div>

      <Canvas
        shadows
        camera={{ position: [1.5, .6, .6], fov: 60 }}
        style={{ width: "100%", height: "100vh", background: "#111" }}
      >
        <ambientLight intensity={0.5} />
        <directionalLight
          position={[5, 5, 5]}
          intensity={1}
          castShadow
          shadow-mapSize-width={2048}
          shadow-mapSize-height={2048}
        />
        <mesh receiveShadow rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
          <planeGeometry args={[10, 10]} />
          <meshStandardMaterial color="#444" />
        </mesh>
       <Grid
          cellSize={1}
          sectionSize={10}
          infiniteGrid={false}
          position={[0, 0.001, 0]} // slight offset to prevent z-fighting
        />
        <Suspense fallback={null}>
          <URDFModel path="/models/urdf/arctos_urdf.urdf" jointAngles={jointAngles} gripperPosition={telemetry?.gripper_position} />
        </Suspense>
        <OrbitControls />
      </Canvas>
    </div>
  );
};
export default RoboticArmViewer;
