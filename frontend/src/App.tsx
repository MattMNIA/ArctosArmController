import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ThemeProvider } from './components/ThemeProvider';
import Navigation from './components/Navigation';
import LandingPage from './pages/LandingPage';
import RobotControl from './pages/RobotControl';
import MotorStatus from './pages/MotorStatus';
import ArmDashboard from './pages/ArmDashboard';
import MotorHoming from './pages/MotorHoming';
import ArmVisualization from './pages/ArmVisualization';
import MotorConfig from './pages/MotorConfig';
import PIDTuning from './pages/PIDTuning';
import IKTesting from './pages/IKTesting';
import { isPrivateBuild } from './utils/buildFlags';

function App() {
  const [currentPage, setCurrentPage] = useState('landing');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 3000); // 4 seconds loading
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (isLoading) {
      // Preload demo media images and gifs
      const demoImages = [
        '/media/Cropped%20Duck.gif',
        '/media/Holding%20Duck.JPG',
        '/media/Modular%20Table%20Mount.JPG',
        '/media/Cropped%20Homing.gif'
      ];
      demoImages.forEach(src => {
        const img = new Image();
        img.src = src;
      });
    }
  }, [isLoading]);

  // allow private pages when either we built a private bundle or we're running locally
  const isLocalHost = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
  const allowPrivate = isPrivateBuild || isLocalHost;

  const renderPage = () => {
    switch (currentPage) {
      case 'landing':
        return <LandingPage />;
      case 'status':
        return allowPrivate ? <MotorStatus /> : <LandingPage />;
      case 'dashboard':
        return allowPrivate ? <ArmDashboard /> : <LandingPage />;
      case 'homing':
        return allowPrivate ? <MotorHoming /> : <LandingPage />;
      case 'visualization':
        return allowPrivate ? <ArmVisualization /> : <LandingPage />;
      case 'config':
        return allowPrivate ? <MotorConfig /> : <LandingPage />;
      case 'control':
        return allowPrivate ? <RobotControl /> : <LandingPage />;
      case 'pid-tuning':
        return allowPrivate ? <PIDTuning /> : <LandingPage />;
      case 'ik-testing':
        return allowPrivate ? <IKTesting /> : <LandingPage />;
      default:
        return allowPrivate ? <RobotControl /> : <LandingPage />;
    }
  };

  // Loading screen component
  const SystemBootUp = ({ onSkip }: { onSkip: () => void }) => {
    const [displayed, setDisplayed] = useState("");
    const [showEllipses, setShowEllipses] = useState(true);
    const text = "Initializing F.E.R.B System";
    const ellipses = "...";

    useEffect(() => {
      let i = 0;
      const interval = setInterval(() => {
        setDisplayed(text.slice(0, i + 1));
        i++;
        if (i === text.length) {
          clearInterval(interval);
        }
      }, 30);
      return () => clearInterval(interval);
    }, []);

    useEffect(() => {
      if (displayed === text) {
        const blinkInterval = setInterval(() => {
          setShowEllipses(prev => !prev);
        }, 500);
        return () => clearInterval(blinkInterval);
      }
    }, [displayed, text]);

    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-black text-green-400 p-4" onClick={onSkip}>
        <div className="text-center">
          <motion.pre
            className="text-2xl font-mono whitespace-pre-line mb-8"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            {displayed}{displayed === text && (showEllipses ? ellipses : "   ")}
          </motion.pre>
        </div>
      </div>
    );
  };

  if (isLoading) {
    return <SystemBootUp onSkip={() => setIsLoading(false)} />;
  }

  return (
    <ThemeProvider>
      <div className="min-h-screen">
        <Navigation currentPage={currentPage} onNavigate={setCurrentPage} />
        
        <main className="pt-16">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentPage}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              {renderPage()}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </ThemeProvider>
  );
}

export default App;
