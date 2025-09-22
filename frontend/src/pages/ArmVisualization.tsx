import React, { Suspense, useEffect, useState, useRef } from "react";
import { Canvas, useLoader } from "@react-three/fiber";
import { OrbitControls, Grid } from "@react-three/drei";
import URDFLoader from "urdf-loader";
import * as THREE from "three";
import io, { Socket } from 'socket.io-client';

interface URDFProps {
  path: string;
  jointAngles: number[];
}

interface TelemetryData {
  state: string;
  q: number[];
  error: number[];
  limits: any[];
}

const URDFModel: React.FC<URDFProps> = ({ path, jointAngles }) => {
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

  // Apply joint angles when they change
  React.useEffect(() => {
    if (urdf && jointAngles.length >= 6) {
      try {
        // Set joint values for the 6 revolute joints
        const jointNames = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6'];

        jointNames.forEach((jointName, index) => {
          if (urdf.joints && urdf.joints[jointName]) {
            urdf.joints[jointName].setJointValue(jointAngles[index] || 0);
          }
        });
      } catch (error) {
        console.error('Error setting joint values:', error);
      }
    }
  }, [urdf, jointAngles]);

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
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    // Connect to websocket
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

    socket.on('telemetry', (data: TelemetryData) => {
      setTelemetry(data);
    });

    socket.on('connect_error', (error) => {
      console.error('WebSocket connection error:', error);
      setConnected(false);
    });

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, []);

  // Default joint angles if no telemetry received
  const jointAngles = telemetry?.q || [0, 0, 0, 0, 0, 0];

  return (
    <div className="relative w-full h-screen bg-gray-900">
      {/* Connection Status Indicator */}
      <div className="absolute top-4 left-4 z-10 flex items-center space-x-2 bg-gray-800/80 backdrop-blur-sm rounded-lg px-3 py-2">
        <div className={`w-3 h-3 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`} />
        <span className="text-sm text-white">
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

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
          <URDFModel path="/models/urdf/arctos_urdf.urdf" jointAngles={jointAngles} />
        </Suspense>
        <OrbitControls />
      </Canvas>
    </div>
  );
};
export default RoboticArmViewer;
