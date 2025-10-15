import { motion } from 'framer-motion';
// AnimatedButton intentionally not used in public landing page
import { PageHeader } from '../components/layout/PageHeader';
// theme helper not needed — Arctos uses dark-only styles

type DemoMediaType = 'photo' | 'gif' | 'video';

interface DemoMediaItem {
  id: string;
  type: DemoMediaType;
  title: string;
  description: string;
  src: string;
  thumbnail?: string;
}

const demoMedia: DemoMediaItem[] = [
  {
    id: 'hero-gif',
    type: 'gif',
    title: 'FERB: Teleoperation Overview',
    description: 'A brief demonstration of teleoperation with handtracking',
    src: '/media/Cropped%20Duck.gif',
  },
  {
    id: 'precision-photo',
    type: 'photo',
    title: 'Precision Pick & Place',
    description: 'Macro shot showing end effector alignment with millimeter-level accuracy.',
    src: '/media/Holding%20Duck.JPG',
  },
  {
    id: 'table-mount-photo',
    type: 'photo',
    title: 'Modular Table Mount',
    description: 'A photo of the modular table mount for the Arctos Arm.',
    src: '/media/Modular%20Table%20Mount.JPG',
  },
  {
    id: 'homing-gif',
    type: 'gif',
    title: 'Motor Homing',
    description: 'GIF demonstrating the homing process for each motor.',
    src: '/media/Cropped%20Homing.gif',
  },
];

const featureHighlights = [
  {
    title: 'Low-Latency Teleoperation',
    detail: 'Websocket control loop tuned for sub-20 ms latency with safety fallbacks.',
  },
  {
    title: 'Cinematic Simulation',
    detail: 'Side-by-side URDF preview and real footage for calibration and storytelling.',
  },
  {
    title: 'Custom Motion Planning',
    detail: 'Hybrid IK and graph-based planner optimized for smooth, collision-aware arcs.',
  },
  {
    title: 'Modular Input Stack',
    detail: 'Gamepad, gesture tracker, and scripted sequences coexist through a unified queue.',
  },
];

const technicalSpecs = [
  { label: 'Degrees of Freedom', value: '6 + gripper' },
  { label: 'Controller Refresh', value: '5KHz PID loop' },
  { label: 'Telemetry Window', value: '20+ real-time metrics' },
  { label: 'Simulation Engines', value: 'PyBullet, URDF WebGL, Custom Visualizer' },
  { label: 'Safety Systems', value: 'E-stop relay, soft limit enforcement, fault alerts' },
  { label: 'Interfaces', value: 'Web dashboard, REST API, Python SDK' },
];

const roadmap = [
  {
    title: 'Advanced Computer Vision & Object Detection',
    target: 'Winter 2025',
    description: 'Real-time YOLO-based object detection with semantic segmentation for autonomous grasping. Integration of depth perception and 3D object pose estimation for complex manipulation tasks.',
  },
  
  {
    title: 'Remote Demo Portal',
    target: 'Winter 2025',
    description: 'Invite collaborators to queue commands remotely through this website.',
  },
  {
    title: 'Realistic Physics Simulation for ML Training',
    target: 'Spring 2026',
    description: 'High-fidelity physics simulation with realistic material properties, friction, and dynamics for training reinforcement learning models on complex manipulation tasks.',
  },
];

export default function LandingPage() {
  return (
    <div>
      <Hero />
      <DemoGallery />
      <FeatureGrid />
      <SpecsSection />
      <RoadmapSection />
    </div>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden bg-slate-950 text-slate-100">
      <div className="relative mx-auto flex w-full max-w-5xl flex-col items-center gap-6 px-6 py-24 text-center">
        <motion.span
          className="inline-flex items-center rounded-full border border-blue-400/40 bg-blue-400/10 px-4 py-2 text-xs font-semibold uppercase tracking-widest text-blue-200"
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          F.E.R.B. Arm Overview
        </motion.span>

        <motion.h1
          className="text-4xl font-black leading-tight text-white sm:text-5xl md:text-6xl"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          Showcasing the<br /> <span className="text-blue-400">F</span>ully <span className="text-blue-400">E</span>ngineered <span className="text-blue-400">R</span>obotic <span className="text-blue-400">B</span>eing
        </motion.h1>

        <motion.p
          className="max-w-2xl text-lg text-slate-300"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          Learn about the design, control system, and features of the FERB throughout the assembly process.
        </motion.p>

        {/* Buttons intentionally removed for public view */}
      </div>
    </section>
  );
}

function DemoGallery() {
  return (
    <section className="bg-slate-950 py-20">
      <div className="mx-auto w-full max-w-6xl px-6 md:px-10">
        <PageHeader
          title="Demo Media"
          description=""
          centered
          animate={false}
        />

        <div className="mt-12 grid grid-cols-1 gap-8 md:grid-cols-2">
          {demoMedia.map((item) => (
            <motion.article
              key={item.id}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ duration: 0.4 }}
              className="overflow-hidden rounded-3xl border border-white/10 bg-white/5 backdrop-blur"
            >
              <div className="relative">
                {item.type === 'video' ? (
                  <div className="relative aspect-video w-full bg-slate-900">
                    <img
                      src={item.thumbnail ?? item.src}
                      alt={`${item.title} poster frame`}
                      className="h-full w-full object-cover"
                    />
                    <span className="absolute inset-0 flex items-center justify-center">
                      <span className="flex h-16 w-16 items-center justify-center rounded-full bg-white/20 text-white backdrop-blur-lg">
                        ▶
                      </span>
                    </span>
                  </div>
                ) : (
                  <img
                    src={item.src}
                    alt={item.title}
                    className="block h-full w-full object-cover"
                  />
                )}
                <span className="absolute left-4 top-4 rounded-full bg-slate-950/80 px-3 py-1 text-xs font-medium uppercase tracking-widest text-slate-200">
                  {item.type}
                </span>
              </div>

              <div className="space-y-2 px-6 py-6">
                <h3 className="text-xl font-semibold text-white">{item.title}</h3>
                <p className="text-sm text-slate-300">{item.description}</p>
              </div>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}

function FeatureGrid() {
  return (
    <section className="bg-slate-900 py-20">
      <div className="mx-auto w-full max-w-6xl px-6 md:px-10">
        <PageHeader
          title="Feature Highlights"
          description=""
          centered
          animate={false}
        />

        <div className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-2">
          {featureHighlights.map((feature) => (
            <motion.div
              key={feature.title}
              className="rounded-2xl border border-white/10 bg-white/[0.06] p-6 shadow-lg shadow-black/10"
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.2 }}
              transition={{ duration: 0.35 }}
            >
              <h3 className="text-lg font-semibold text-white">{feature.title}</h3>
              <p className="mt-3 text-sm text-slate-300">{feature.detail}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function SpecsSection() {
  return (
    <section className="bg-slate-950 py-20">
      <div className="mx-auto w-full max-w-5xl px-6 md:px-10">
        <PageHeader
          title="Technical Specs"
          description=""
          centered
          animate={false}
        />

        <div className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-2">
          {technicalSpecs.map((spec) => (
            <motion.dl
              key={spec.label}
              className="flex flex-col rounded-2xl border border-white/10 bg-white/[0.05] p-5"
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ duration: 0.3 }}
            >
              <dt className="text-sm uppercase tracking-wider text-slate-400">{spec.label}</dt>
              <dd className="mt-2 text-lg font-medium text-white">{spec.value}</dd>
            </motion.dl>
          ))}
        </div>
      </div>
    </section>
  );
}

function RoadmapSection() {
  return (
    <section className="bg-slate-900 py-20">
      <div className="mx-auto w-full max-w-5xl px-6 md:px-10">
        <PageHeader
          title="Plans for the Future"
          description=""
          centered
          animate={false}
        />

        <ol className="mt-12 space-y-10">
          {roadmap.map((item, index) => (
            <motion.li
              key={item.title}
              className="relative rounded-2xl border border-white/10 bg-white/[0.05] p-6"
              initial={{ opacity: 0, y: 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.25 }}
              transition={{ duration: 0.35, delay: index * 0.05 }}
            >
              <span className="absolute -left-3 top-6 hidden h-6 w-6 items-center justify-center rounded-full border border-blue-400/40 bg-slate-950 text-sm font-semibold text-blue-300 shadow-md shadow-blue-500/25 sm:flex">
                {index + 1}
              </span>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-baseline sm:justify-between">
                <h3 className="text-xl font-semibold text-white">{item.title}</h3>
                <span className="text-sm font-medium uppercase tracking-widest text-blue-200">
                  {item.target}
                </span>
              </div>
              <p className="mt-3 text-sm text-slate-300">{item.description}</p>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}
