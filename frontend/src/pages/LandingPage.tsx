import { motion } from 'framer-motion';
import { AnimatedButton } from '../components/ui/AnimatedButton';
import { PageHeader } from '../components/layout/PageHeader';

interface LandingPageProps {
  onNavigate?: (page: string) => void;
}

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
    id: 'hero-video',
    type: 'video',
    title: 'Arctos Arm: Quick Overview',
    description: 'A fast walkthrough of the teleoperation workflow and arm motion sequences.',
    src: 'https://placehold.co/1280x720/0f172a/ffffff?text=Video+Placeholder',
    thumbnail: 'https://placehold.co/640x360/1e293b/94a3b8?text=Video+Poster',
  },
  {
    id: 'precision-photo',
    type: 'photo',
    title: 'Precision Pick & Place',
    description: 'Macro shot showing end effector alignment with millimeter-level accuracy.',
    src: 'https://placehold.co/800x600/0f172a/ffffff?text=Photo+Placeholder',
  },
  {
    id: 'gesture-gif',
    type: 'gif',
    title: 'Gesture Control Loop',
    description: 'GIF illustrating the live teleop dashboard mirroring wrist and finger movement.',
    src: 'https://placehold.co/800x600/1e293b/ffffff?text=GIF+Placeholder',
  },
  {
    id: 'safety-photo',
    type: 'photo',
    title: 'Safety & Diagnostics',
    description: 'Diagnostic overlay showcasing real-time torque, current, and thermal readings.',
    src: 'https://placehold.co/800x600/111827/ffffff?text=Photo+Placeholder',
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
  { label: 'Controller Refresh', value: '500 Hz PID loop' },
  { label: 'Telemetry Window', value: '20+ real-time metrics' },
  { label: 'Simulation Engines', value: 'PyBullet, URDF WebGL, Custom Visualizer' },
  { label: 'Safety Systems', value: 'E-stop relay, soft limit enforcement, fault alerts' },
  { label: 'Interfaces', value: 'Web dashboard, REST API, Python SDK' },
];

const roadmap = [
  {
    title: 'Autonomous Sequencing Toolkit',
    target: 'Winter 2025',
    description: 'Blend teleop and scripted moves using an editable timeline with physics-aware preview.',
  },
  {
    title: 'Haptic Feedback Integration',
    target: 'Spring 2026',
    description: 'Bi-directional force cues streamed to glove controllers for richer telepresence.',
  },
  {
    title: 'Remote Demo Portal',
    target: 'Summer 2026',
    description: 'Invite collaborators to queue commands and replay highlight reels from anywhere.',
  },
];

export default function LandingPage({ onNavigate }: LandingPageProps) {
  return (
    <div className="bg-slate-950 text-slate-100">
      <Hero onNavigate={onNavigate} />
      <DemoGallery />
      <FeatureGrid />
      <SpecsSection />
      <RoadmapSection />
    </div>
  );
}

function Hero({ onNavigate }: LandingPageProps) {
  return (
    <section className="relative overflow-hidden bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(59,130,246,0.15),transparent_55%)]" />
      <div className="relative mx-auto flex w-full max-w-5xl flex-col items-center gap-6 px-6 py-24 text-center">
        <motion.span
          className="inline-flex items-center rounded-full border border-blue-400/40 bg-blue-400/10 px-4 py-2 text-xs font-semibold uppercase tracking-widest text-blue-200"
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          Arctos Arm Demo
        </motion.span>

        <motion.h1
          className="text-4xl font-black leading-tight text-white sm:text-5xl md:text-6xl"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          Showcasing a Robotic Arm Built to Perform IRL
        </motion.h1>

        <motion.p
          className="max-w-2xl text-lg text-slate-300"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          Explore live demos, feature walkthroughs, and future plans for the Arctos teleoperated arm. This page is a living scrapbook—swap in your own footage, screenshots, and highlight reels to tell the story of the build.
        </motion.p>

        <div className="flex flex-wrap justify-center gap-4">
          <AnimatedButton
            size="lg"
            onClick={() => onNavigate?.('control')}
            className="shadow-lg shadow-blue-500/20"
          >
            Launch Control Interface
          </AnimatedButton>
          <AnimatedButton
            size="lg"
            variant="ghost"
            className="border-white/20 bg-white/10 text-white hover:bg-white/20"
            onClick={() => onNavigate?.('visualization')}
          >
            Open Simulation View
          </AnimatedButton>
        </div>
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
          description="Swap these placeholders with GIFs, photos, or video clips from your builds and presentations."
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
          description="Capture the talking points you cover during demos—what makes this robotic arm unique?"
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
          description="Keep the numbers handy—swap in the precise specs that matter to your audience."
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
          description="Outline the next milestones so viewers know where the project is headed."
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
