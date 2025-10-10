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
import ArmShowcasePage from './pages/ArmShowcasePage';
import MotorConfig from './pages/MotorConfig';

function App() {
  const [currentPage, setCurrentPage] = useState('landing');

  const renderPage = () => {
    switch (currentPage) {
      case 'landing':
        return <LandingPage onNavigate={setCurrentPage} />;
      case 'status':
        return <MotorStatus />;
      case 'dashboard':
        return <ArmDashboard />;
      case 'simulation':
        return <SimulationVideo />;
      case 'homing':
        return <MotorHoming />;
      case 'visualization':
        return <ArmVisualization />;
      case 'arm-showcase':
        return <ArmShowcasePage onNavigate={setCurrentPage} />;
      case 'config':
        return <MotorConfig />;
      case 'control':
        return <RobotControl />;
      default:
        return <RobotControl />;
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
