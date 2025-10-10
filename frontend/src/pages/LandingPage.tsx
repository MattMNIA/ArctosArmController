import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { AnimatedButton } from '../components/ui/AnimatedButton';
import { PageHeader } from '../components/layout/PageHeader';
import { cn } from '../utils/cn';
import ArctosArmScene from '../components/ArctosArmScene';

interface LandingPageProps {
  onNavigate?: (page: string) => void;
}

interface FloatingControl {
  id: string;
  label: string;
  top: string;
  left: string;
  hue: string;
  delay: number;
}

interface ShowcaseItem {
  id: string;
  title: string;
  description: string;
  type: 'image' | 'video';
  src: string;
  poster?: string;
}

interface Milestone {
  id: string;
  date: string;
  title: string;
  description: string;
  media: { src: string; alt: string };
  highlights: string[];
}

function FloatingControls({ onNavigate }: { onNavigate?: (page: string) => void }) {
  const controls: FloatingControl[] = useMemo(
    () => [
      {
        id: 'precision',
        label: 'Precision Move',
        top: '12%',
        left: '12%',
        hue: 'from-blue-500/80 via-blue-400/80 to-blue-300/80',
        delay: 0,
      },
      {
        id: 'teleop',
        label: 'Live Teleop',
        top: '65%',
        left: '18%',
        hue: 'from-purple-500/80 via-purple-400/80 to-indigo-300/80',
        delay: 0.35,
      },
      {
        id: 'simulate',
        label: 'Run Simulation',
        top: '20%',
        left: '70%',
        hue: 'from-cyan-500/80 via-teal-400/80 to-emerald-300/80',
        delay: 0.55,
      },
      {
        id: 'estop',
        label: 'Emergency Stop',
        top: '72%',
        left: '68%',
        hue: 'from-rose-600/80 via-orange-500/80 to-amber-400/80',
        delay: 0.8,
      },
    ],
    []
  );

  return (
    <div className="pointer-events-none absolute inset-0">
      {controls.map((control) => (
        <motion.button
          key={control.id}
          onClick={() => onNavigate?.('control')}
          className={`pointer-events-auto absolute flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold text-white shadow-lg backdrop-blur-md transition-transform duration-200 hover:scale-105 bg-gradient-to-br ${control.hue}`}
          style={{ top: control.top, left: control.left }}
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{
            opacity: 1,
            scale: [1, 1.05, 1],
            y: [0, -10, 0],
            x: [0, 6, 0],
          }}
          transition={{
            repeat: Infinity,
            repeatType: 'mirror',
            duration: 6,
            delay: control.delay,
            ease: 'easeInOut',
          }}
        >
          <span className="h-2 w-2 rounded-full bg-white/80" />
          {control.label}
        </motion.button>
      ))}
    </div>
  );
}

function HeroSection({ onNavigate }: { onNavigate?: (page: string) => void }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [canvasElement, setCanvasElement] = useState<HTMLCanvasElement | null>(null);

  const handleContextLost = useCallback((event: Event) => {
    event.preventDefault();
  }, []);

  const handleContextRestored = useCallback(() => {
    // noop for now but keeps the listener symmetrical and ready for future hooks
  }, []);

  useEffect(() => {
    const canvas = canvasElement;
    if (!canvas) return;

    canvas.addEventListener('webglcontextlost', handleContextLost, false);
    canvas.addEventListener('webglcontextrestored', handleContextRestored, false);

    return () => {
      canvas.removeEventListener('webglcontextlost', handleContextLost, false);
      canvas.removeEventListener('webglcontextrestored', handleContextRestored, false);
    };
  }, [canvasElement, handleContextLost, handleContextRestored]);

  return (
    <section className="relative overflow-hidden bg-gradient-to-b from-slate-950 via-gray-950 to-slate-950">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(59,130,246,0.25),transparent_55%)]" />
      <div className="absolute inset-x-0 top-0 h-72 bg-gradient-to-b from-white/5 via-transparent to-transparent blur-3xl" />

      <div className="relative mx-auto flex w-full max-w-7xl flex-col px-6 pt-28 pb-16 md:px-12">
        <div className="relative h-[72vh] min-h-[560px] w-full overflow-hidden rounded-[3.75rem] border border-white/5 bg-slate-950/60 shadow-[0_60px_140px_-70px_rgba(59,130,246,0.6)]">
          <ArctosArmScene
            className="absolute inset-0 z-0 h-full w-full"
            shadows
            dpr={[1, 2]}
            camera={{ position: [5.6, 3.4, 6.9], fov: 40 }}
            gl={{ antialias: true, powerPreference: 'high-performance' }}
            fallback={null}
            showButton
            onNavigate={onNavigate}
            onCanvasCreated={(gl) => {
              canvasRef.current = gl.domElement;
              setCanvasElement(gl.domElement);
            }}
          />

          <div className="pointer-events-none absolute inset-0 z-10 bg-gradient-to-t from-slate-950/75 via-slate-950/25 to-transparent" />

          <div className="absolute inset-0 z-20">
            <FloatingControls onNavigate={onNavigate} />
          </div>

          <div className="absolute bottom-0 left-0 right-0 z-30 flex justify-center px-6 pb-10">
            <motion.div
              initial={{ opacity: 0, y: 40 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.15 }}
              className="pointer-events-auto w-full max-w-4xl rounded-3xl border border-white/10 bg-white/[0.07] p-8 shadow-2xl shadow-blue-500/15 backdrop-blur-xl"
            >
              <div className="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-xl">
                  <span className="inline-flex items-center rounded-full border border-blue-500/40 bg-blue-500/15 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-blue-100">
                    Robotics + Teleoperation
                  </span>
                  <h1 className="mt-6 text-4xl font-black leading-tight text-white sm:text-5xl md:text-[3.35rem] md:leading-[1.05]">
                    Bring the Arctos Arm to Life with a Flash of Motion
                  </h1>
                  <p className="mt-6 text-base text-slate-100/80">
                    ArctosArm merges precise kinematics, responsive control, and immersive simulation to deliver a robotic arm you can feel. Explore the command center, stream live telemetry, and choreograph cinematic motion with confidence.
                  </p>
                  <div className="mt-7 flex flex-wrap gap-4">
                    <AnimatedButton
                      size="lg"
                      onClick={() => onNavigate?.('control')}
                      variant="primary"
                      className="shadow-blue-500/30"
                    >
                      Launch Control Suite
                    </AnimatedButton>
                    <AnimatedButton
                      size="lg"
                      variant="ghost"
                      className="border-white/20 bg-white/10 text-white hover:bg-white/25"
                      onClick={() => onNavigate?.('visualization')}
                    >
                      View 3D Simulation
                    </AnimatedButton>
                  </div>
                </div>
                <div className="grid flex-shrink-0 grid-cols-3 gap-4 text-center text-sm text-slate-100/70">
                  <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
                    <p className="text-3xl font-bold text-white">6</p>
                    <p>Degrees of freedom with adaptive PID control.</p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
                    <p className="text-3xl font-bold text-white">15 ms</p>
                    <p>Telemetry latency over low-lag websocket streams.</p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
                    <p className="text-3xl font-bold text-white">4+</p>
                    <p>Simulation backends including PyBullet and URDF preview.</p>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}

function ShowcaseSection() {
  const showcaseItems: ShowcaseItem[] = useMemo(
    () => [
      {
        id: 'overview-video',
        title: 'Immersive Control Feedback',
        description:
          'Blend tactile teleoperation with visual overlays. Responsive UI tiles reflect torque, velocity, and joint health the instant it changes.',
        type: 'video',
        src: 'https://storage.googleapis.com/coverr-main/assets/coverr-robotics-lab-5056.mp4',
        poster: 'https://images.unsplash.com/photo-1580927752452-89d86da3fa0a?auto=format&fit=crop&w=1200&q=80',
      },
      {
        id: 'arm-studio',
        title: 'Simulation Meets Reality',
        description:
          'Stream a URDF-driven render beside the live arm feed. Calibration overlays keep the digital twin locked to the physical robot.',
        type: 'image',
        src: 'https://images.unsplash.com/photo-1581091012184-7af9910d2c34?auto=format&fit=crop&w=1200&q=80',
      },
      {
        id: 'gesture',
        title: 'Gesture-driven Inputs',
        description:
          'Translate human gestures into smooth motion cues. A responsive queue ensures seamless blending between prerecorded paths and manual overrides.',
        type: 'image',
        src: 'https://images.unsplash.com/photo-1527430253228-e93688616381?auto=format&fit=crop&w=1200&q=80',
      },
    ],
    []
  );

  return (
    <section className="bg-slate-950 py-24">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-14 px-6 md:px-10">
        <PageHeader
          title="Why ArctosArm Feels Different"
          description="A unified workspace that brings planning, teleoperation, and simulation together with cinematic feedback."
          centered
          animate={false}
        />

        <div className="grid grid-cols-1 gap-10 md:grid-cols-2">
          {showcaseItems.map((item) => (
            <motion.article
              key={item.id}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.1 }}
              viewport={{ once: true, amount: 0.4 }}
              className="group relative overflow-hidden rounded-3xl border border-white/5 bg-white/[0.02] shadow-xl shadow-black/40"
            >
              <div className="relative h-72 w-full overflow-hidden">
                {item.type === 'video' ? (
                  <video
                    src={item.src}
                    poster={item.poster}
                    autoPlay
                    loop
                    muted
                    playsInline
                    className="h-full w-full object-cover transition-transform duration-[5500ms] group-hover:scale-105"
                  />
                ) : (
                  <img
                    src={item.src}
                    alt={item.title}
                    className="h-full w-full object-cover transition-transform duration-[5500ms] group-hover:scale-105"
                    loading="lazy"
                  />
                )}
              </div>
              <div className="space-y-3 p-8">
                <h3 className="text-2xl font-bold text-white">{item.title}</h3>
                <p className="text-base text-slate-300/80">{item.description}</p>
              </div>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}

function MilestoneCard({
  milestone,
  align,
}: {
  milestone: Milestone;
  align: 'left' | 'right' | 'mobile';
}) {
  const isLeft = align === 'left';

  return (
    <article
      className={cn(
        'group relative overflow-hidden rounded-3xl border border-white/5 bg-white/[0.03] shadow-xl shadow-black/40 backdrop-blur-sm',
        align === 'mobile'
          ? 'w-full pl-6 before:absolute before:left-3 before:top-0 before:h-full before:w-px before:bg-gradient-to-b before:from-transparent before:via-blue-400/40 before:to-transparent before:content-[""]'
          : 'max-w-xl',
        isLeft ? 'md:text-right md:ml-auto' : ''
      )}
    >
      <div className="relative h-48 w-full overflow-hidden">
        <img
          src={milestone.media.src}
          alt={milestone.media.alt}
          className="h-full w-full object-cover transition-transform duration-[5500ms] group-hover:scale-105"
          loading="lazy"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-slate-950/70 via-transparent to-transparent" />
        <span
          className={cn(
            'absolute top-4 inline-flex items-center rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-white shadow-sm shadow-white/10',
            isLeft ? 'right-4' : 'left-4'
          )}
        >
          {milestone.date}
        </span>
      </div>
      <div
        className={cn(
          'space-y-4 p-6',
          isLeft ? 'md:text-right md:items-end md:flex md:flex-col md:gap-4' : ''
        )}
      >
        <div className={cn(isLeft ? 'md:self-end md:text-right' : '')}>
          <h3 className="text-2xl font-bold text-white">{milestone.title}</h3>
          <p className="mt-3 text-base text-slate-300/80">{milestone.description}</p>
        </div>
        <ul
          className={cn(
            'space-y-3 text-sm text-slate-200/80',
            isLeft ? 'md:text-right' : ''
          )}
        >
          {milestone.highlights.map((highlight) => (
            <li
              key={highlight}
              className={cn(
                'flex items-start gap-3',
                isLeft ? 'md:flex-row-reverse md:text-right' : ''
              )}
            >
              <span className="mt-1 h-2.5 w-2.5 flex-shrink-0 rounded-full bg-emerald-400" />
              <span>{highlight}</span>
            </li>
          ))}
        </ul>
      </div>
    </article>
  );
}

function ProgressTimeline() {
  const milestones: Milestone[] = useMemo(
    () => [
      {
        id: 'milestone-oct',
        date: 'October 2025',
        title: 'Haptic Telepresence Rollout',
        description:
          'Live joint feedback now drives adaptive grip forces while streaming into the teleop dashboard.',
        media: {
          src: 'https://images.unsplash.com/photo-1587620931276-d97f425f62b9?auto=format&fit=crop&w=1200&q=80',
          alt: 'Operator manipulating a robotic arm through a control station',
        },
        highlights: [
          'Integrated bi-directional torque feedback with smoothing filters.',
          'Added animated telemetry tags to the Robot Control page.',
          'Expanded safety interlocks with staged emergency stop routines.',
        ],
      },
      {
        id: 'milestone-sep',
        date: 'September 2025',
        title: 'Motion Planning Revamp',
        description:
          'A new hybrid planner blends inverse kinematics seeds with graph search for obstacle-aware moves.',
        media: {
          src: 'https://images.unsplash.com/photo-1534723328310-e82dad3ee43f?auto=format&fit=crop&w=1200&q=80',
          alt: 'Visualizer showing a robotic arm path in a 3D workspace',
        },
        highlights: [
          'Shipped trajectory preview overlays to the Arm Dashboard.',
          'Enabled multi-goal queueing with live re-ordering.',
          'Reduced planning time by 43% with cached Jacobians.',
        ],
      },
      {
        id: 'milestone-aug',
        date: 'August 2025',
        title: 'Simulation Fidelity Upgrade',
        description:
          'PyBullet and URDF views now remain in pixel-perfect sync thanks to a calibration pipeline.',
        media: {
          src: 'https://images.unsplash.com/photo-1569025690938-a00729c9e1b9?auto=format&fit=crop&w=1200&q=80',
          alt: 'Robotic arm simulation displayed on multiple monitors',
        },
        highlights: [
          'Implemented asynchronous video streaming with health checks.',
          'Added dynamic lighting presets for the 3D viewer.',
          'Launched pose bookmarking to capture repeatable shots.',
        ],
      },
    ],
    []
  );

  return (
    <section className="relative bg-slate-950 py-24">
      <div className="pointer-events-none absolute inset-y-0 left-1/2 hidden md:block">
        <div className="h-full w-px -translate-x-1/2 bg-gradient-to-b from-transparent via-white/10 to-transparent" />
      </div>

      <div className="mx-auto w-full max-w-6xl px-6 md:px-10">
        <PageHeader
          title="Progress Journal"
          description="Follow the engineering milestones, complete with snapshots and release notes."
          centered
          animate={false}
        />

        <div className="mt-16 space-y-16">
          {milestones.map((milestone, index) => {
            const isLeft = index % 2 === 0;

            return (
              <motion.div
                key={milestone.id}
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.3 }}
                transition={{ duration: 0.55, delay: index * 0.08 }}
                className="relative grid gap-8 md:grid-cols-[1fr_auto_1fr] md:items-center"
              >
                <div className="hidden md:block md:pr-10 md:self-stretch">
                  {isLeft ? (
                    <MilestoneCard milestone={milestone} align="left" />
                  ) : (
                    <div aria-hidden className="h-full" />
                  )}
                </div>

                <div className="flex justify-center md:col-start-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full border border-blue-300/50 bg-slate-950 shadow-lg shadow-blue-500/20">
                    <span className="h-2.5 w-2.5 rounded-full bg-blue-400" />
                  </span>
                </div>

                <div className="hidden md:block md:pl-10 md:self-stretch">
                  {!isLeft ? (
                    <MilestoneCard milestone={milestone} align="right" />
                  ) : (
                    <div aria-hidden className="h-full" />
                  )}
                </div>

                <div className="md:hidden">
                  <MilestoneCard milestone={milestone} align="mobile" />
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export default function LandingPage({ onNavigate }: LandingPageProps) {
  return (
    <div className="bg-slate-950 text-white">
      <HeroSection onNavigate={onNavigate} />
      <ShowcaseSection />
      <ProgressTimeline />
    </div>
  );
}
