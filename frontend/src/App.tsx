import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ThemeProvider } from './components/ThemeProvider';
import Navigation from './components/Navigation';
import LandingPage from './pages/LandingPage';
import RobotControl from './pages/RobotControl';
import MotorStatus from './pages/MotorStatus';
import ArmDashboard from './pages/ArmDashboard';
import SimulationVideo from './pages/SimulationVideo';
import MotorHoming from './pages/MotorHoming';
import ArmVisualization from './pages/ArmVisualization';
import MotorConfig from './pages/MotorConfig';
import { isPrivateBuild } from './utils/buildFlags';
import CameraConfig from './pages/CameraConfig';

function App() {
  const [currentPage, setCurrentPage] = useState('landing');

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
      case 'simulation':
        return allowPrivate ? <SimulationVideo /> : <LandingPage />;
      case 'homing':
        return allowPrivate ? <MotorHoming /> : <LandingPage />;
      case 'visualization':
        return allowPrivate ? <ArmVisualization /> : <LandingPage />;
      case 'config':
        return allowPrivate ? <MotorConfig /> : <LandingPage />;
      case 'control':
        return allowPrivate ? <RobotControl /> : <LandingPage />;
      default:
        return allowPrivate ? <RobotControl /> : <LandingPage />;
    }
  };

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
