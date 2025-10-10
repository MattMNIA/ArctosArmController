import { Suspense, useCallback, useEffect, useMemo, useRef, type ComponentProps, type ReactNode } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import type { WebGLRenderer, Group, Object3D } from 'three';
import { Quaternion, Vector3 } from 'three';
import { Html } from '@react-three/drei';
import URDFLoader from 'urdf-loader';

interface AnimatedArmModelProps {
  onNavigate?: (page: string) => void;
  showButton?: boolean;
}

function AnimatedArmModel({ onNavigate, showButton = true }: AnimatedArmModelProps) {
  // @ts-ignore - URDFLoader typings are not compatible with useLoader's expected interface
  const urdf = useLoader(
    URDFLoader as unknown as any,
    '/models/urdf/arctos_urdf.urdf',
    (loader: URDFLoader) => {
      loader.packages = {
        '': '/models/meshes/',
      };
      loader.fetchOptions = {
        mode: 'cors',
      };
    }
  ) as any;

  const rootRef = useRef<Group>(null);
  const buttonAnchorRef = useRef<Group>(null);
  const endEffectorRef = useRef<Object3D | null>(null);

  const jointNames = useMemo(
    () => ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6'],
    []
  );

  const worldPosition = useMemo(() => new Vector3(), []);
  const localPosition = useMemo(() => new Vector3(), []);
  const worldQuaternion = useMemo(() => new Quaternion(), []);
  const rootQuaternion = useMemo(() => new Quaternion(), []);

  useEffect(() => {
    if (!urdf) {
      return;
    }

    urdf.rotation.x = -Math.PI / 2;
    urdf.traverse((child: any) => {
      if (child.isMesh) {
        child.castShadow = true;
        child.receiveShadow = true;
      }
    });

    const potentialEffector =
      urdf.getObjectByName('tool0') ??
      urdf.getObjectByName('ee_link') ??
      (urdf.joints?.joint6?.child ?? null);

    if (potentialEffector) {
      endEffectorRef.current = potentialEffector as Object3D;
    }
  }, [urdf]);

  useFrame(({ clock }) => {
    if (!urdf) {
      return;
    }

    const t = clock.getElapsedTime();
    const jointAngles = [
      Math.sin(t * 0.35) * 0.8,
      Math.cos(t * 0.45 + 0.6) * 0.9,
      Math.sin(t * 0.6 + 1.2) * 0.75,
      Math.cos(t * 0.8 + 0.4) * 1.05,
      Math.sin(t * 0.95 + 0.3) * 0.9,
      Math.cos(t * 1.1) * 1.2,
    ];

    jointNames.forEach((name, index) => {
      const joint = urdf.joints?.[name];
      if (joint) {
        joint.setJointValue(jointAngles[index]);
      }
    });

    const jawTarget = (Math.sin(t * 1.6) + 1) * 0.5 * 0.012;
    if (urdf.joints?.jaw1) {
      urdf.joints.jaw1.setJointValue(jawTarget);
    }
    if (urdf.joints?.jaw2) {
      urdf.joints.jaw2.setJointValue(jawTarget);
    }

    if (rootRef.current) {
      rootRef.current.rotation.y = Math.sin(t * 0.18) * 0.25;
    }

    urdf.updateMatrixWorld(true);

    const endEffector = endEffectorRef.current;
    const buttonAnchor = buttonAnchorRef.current;
    const root = rootRef.current;

    if (endEffector && buttonAnchor && root) {
      endEffector.updateMatrixWorld(true);
      endEffector.getWorldPosition(worldPosition);
      localPosition.copy(worldPosition);
      root.worldToLocal(localPosition);
      buttonAnchor.position.lerp(localPosition, 0.18);

      endEffector.getWorldQuaternion(worldQuaternion);
      root.getWorldQuaternion(rootQuaternion);
      rootQuaternion.invert();
      worldQuaternion.premultiply(rootQuaternion);
      buttonAnchor.quaternion.slerp(worldQuaternion, 0.18);
    }
  });

  return (
    <group ref={rootRef} position={[0, -1.35, 0]}>
      <mesh receiveShadow rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.04, 0]}>
        <circleGeometry args={[4.5, 64]} />
        <meshStandardMaterial color="#0b1220" />
      </mesh>

      <primitive object={urdf} />

      {showButton && (
        <group ref={buttonAnchorRef}>
          <Html transform distanceFactor={10} occlude>
            <button
              onClick={() => onNavigate?.('control')}
              className="rounded-2xl bg-gradient-to-br from-blue-500 via-indigo-500 to-purple-500 px-4 py-2 text-xs font-bold uppercase tracking-wide text-white shadow-lg shadow-blue-500/30 transition-transform duration-200 hover:scale-105"
            >
              Queue Task
            </button>
          </Html>
        </group>
      )}
    </group>
  );
}

type CanvasComponentProps = ComponentProps<typeof Canvas>;

export interface ArctosArmSceneProps extends Omit<CanvasComponentProps, 'children'> {
  onNavigate?: (page: string) => void;
  showButton?: boolean;
  fallback?: ReactNode;
  onCanvasCreated?: (gl: WebGLRenderer) => void;
}

export function ArctosArmScene({
  onNavigate,
  showButton = true,
  fallback = null,
  onCanvasCreated,
  onCreated,
  ...rest
}: ArctosArmSceneProps) {
  const handleCreated = useCallback<NonNullable<CanvasComponentProps['onCreated']>>(
    (state) => {
      onCanvasCreated?.(state.gl);
      onCreated?.(state);
    },
    [onCanvasCreated, onCreated]
  );

  return (
    <Suspense fallback={fallback}>
      <Canvas {...rest} onCreated={handleCreated}>
        <color attach="background" args={["#05070d"]} />
        <ambientLight intensity={0.55} />
        <directionalLight
          position={[6, 9, 6]}
          intensity={1.25}
          castShadow
          shadow-mapSize={[2048, 2048]}
        />
        <pointLight position={[-5, 4, -3]} intensity={0.75} color="#22d3ee" />
        <pointLight position={[3, 3, -6]} intensity={0.65} color="#c084fc" />
        <AnimatedArmModel onNavigate={onNavigate} showButton={showButton} />
      </Canvas>
    </Suspense>
  );
}

export default ArctosArmScene;
