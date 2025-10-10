import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { WebGLRenderer } from 'three';
import ArctosArmScene from '../components/ArctosArmScene';
import { AnimatedButton } from '../components/ui/AnimatedButton';
import { cn } from '../utils/cn';

interface ArmShowcasePageProps {
  onNavigate?: (page: string) => void;
}

export default function ArmShowcasePage({ onNavigate }: ArmShowcasePageProps) {
  const rendererRef = useRef<WebGLRenderer | null>(null);
  const [isQueueButtonVisible, setIsQueueButtonVisible] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const [contextLost, setContextLost] = useState(false);
  const [canvasElement, setCanvasElement] = useState<HTMLCanvasElement | null>(null);
  const [, setStatsTick] = useState(0);

  const statusPills = useMemo(
    () => [
      {
        id: 'fps',
        label: 'Renderer',
        value: () => rendererRef.current?.info.render.calls ?? 0,
        formatter: (val: number) => `${val} draw calls`,
      },
      {
        id: 'geometry',
        label: 'Geometry',
        value: () => rendererRef.current?.info.memory.geometries ?? 0,
        formatter: (val: number) => `${val} meshes`,
      },
      {
        id: 'textures',
        label: 'Textures',
        value: () => rendererRef.current?.info.memory.textures ?? 0,
        formatter: (val: number) => `${val} textures`,
      },
    ],
    []
  );

  const attachCanvas = useCallback((gl: WebGLRenderer) => {
    rendererRef.current = gl;
    setCanvasElement(gl.domElement);
  }, []);

  useEffect(() => {
    const canvas = canvasElement;
    if (!canvas) {
      return;
    }

    const handleLost = (event: Event) => {
      event.preventDefault();
      setContextLost(true);
    };

    const handleRestored = () => {
      setContextLost(false);
    };

    canvas.addEventListener('webglcontextlost', handleLost, false);
    canvas.addEventListener('webglcontextrestored', handleRestored, false);

    return () => {
      canvas.removeEventListener('webglcontextlost', handleLost, false);
      canvas.removeEventListener('webglcontextrestored', handleRestored, false);
    };
  }, [canvasElement]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setStatsTick((tick) => tick + 1);
    }, 1000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, []);

  return (
    <div className="relative min-h-[calc(100vh-4rem)] bg-slate-950 text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(59,130,246,0.2),transparent_55%)]" />

      <div className="relative mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 pb-16 pt-10 md:flex-row md:items-stretch md:px-10">
        <div className="relative flex-1 overflow-hidden rounded-3xl border border-white/10 bg-slate-950/80 shadow-[0_50px_120px_-60px_rgba(59,130,246,0.45)]">
          <ArctosArmScene
            className="absolute inset-0"
            shadows
            dpr={[1, 2]}
            camera={{ position: [5.6, 3.4, 6.9], fov: 40 }}
            gl={{ antialias: true, powerPreference: 'high-performance' }}
            showButton={isQueueButtonVisible}
            onNavigate={onNavigate}
            frameloop={isPaused ? 'never' : 'always'}
            onCanvasCreated={attachCanvas}
          />

          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-slate-950/80 via-slate-950/15 to-transparent" />

          {contextLost && (
            <div className="pointer-events-auto absolute inset-0 z-20 flex items-center justify-center bg-slate-950/90 backdrop-blur">
              <div className="rounded-2xl border border-red-400/40 bg-red-900/40 p-6 text-center">
                <p className="text-lg font-semibold text-red-200">WebGL context lost</p>
                <p className="mt-2 text-sm text-red-100/80">
                  Try reloading the page or resizing the window to recover the renderer.
                </p>
              </div>
            </div>
          )}
        </div>

        <aside className="flex w-full max-w-md flex-col gap-6 rounded-3xl border border-white/10 bg-white/[0.05] p-6 shadow-inner shadow-blue-500/10 backdrop-blur-lg">
          <header className="space-y-2">
            <h2 className="text-2xl font-bold">Arm Animation Sandbox</h2>
            <p className="text-sm text-slate-200/75">
              Use this space to experiment with lighting, queue button visibility, and render stability without the rest of the landing page layout.
            </p>
          </header>

          <div className="space-y-4">
            <AnimatedButton
              variant={isQueueButtonVisible ? 'ghost' : 'primary'}
              onClick={() => setIsQueueButtonVisible((prev) => !prev)}
              className="w-full"
            >
              {isQueueButtonVisible ? 'Hide Queue Button' : 'Show Queue Button'}
            </AnimatedButton>
            <AnimatedButton
              variant={isPaused ? 'primary' : 'ghost'}
              onClick={() => setIsPaused((prev) => !prev)}
              className="w-full"
            >
              {isPaused ? 'Resume Motion' : 'Pause Motion'}
            </AnimatedButton>
            <AnimatedButton
              variant="ghost"
              onClick={() => onNavigate?.('landing')}
              className="w-full border border-white/40 text-white hover:bg-white/20"
            >
              Back to Landing Page
            </AnimatedButton>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {statusPills.map((pill) => {
              const value = pill.value();
              return (
                <div
                  key={pill.id}
                  className="rounded-2xl border border-white/10 bg-slate-900/60 p-4 text-sm text-slate-200/75"
                >
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-300/70">
                    {pill.label}
                  </p>
                  <p className="mt-2 text-lg font-bold text-white">
                    {typeof value === 'number' ? pill.formatter(value) : '–'}
                  </p>
                </div>
              );
            })}
          </div>

          <div className="space-y-2 text-xs text-slate-300/70">
            <p className="font-semibold uppercase tracking-wide">Notes</p>
            <ul className="space-y-1">
              <li className="flex items-start gap-2">
                <span className={cn('mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-400')} />
                Motion parameters live inside <code>ArctosArmScene</code>; tweak joint curves there.
              </li>
              <li className="flex items-start gap-2">
                <span className={cn('mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-400')} />
                Event listeners monitor <code>webglcontextlost</code> to help diagnose renderer resets.
              </li>
              <li className="flex items-start gap-2">
                <span className={cn('mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-400')} />
                Toggle pause to confirm joint setters release gracefully when animation stops.
              </li>
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
