import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { getThemeClasses } from '../theme';

interface NavigationProps {
  currentPage: string;
  onNavigate: (page: string) => void;
}

export default function Navigation({ currentPage, onNavigate }: NavigationProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  // Arctos site uses dark mode only
  const darkMode = true;

  const navItems = [
    { id: 'landing', label: 'Overview' },
    { id: 'control', label: 'Robot Control' },
    { id: 'status', label: 'Motor Status' },
    { id: 'dashboard', label: 'Arm Dashboard' },
    { id: 'simulation', label: 'Simulation Video' },
    { id: 'homing', label: 'Motor Homing' },
    { id: 'config', label: 'Motor Config' },
    { id: 'visualization', label: '3D Visualization' },
    { id: 'arm-showcase', label: 'Arm Showcase (Temp)' },
  ];

  // keep an activeSection in sync with currentPage for styling parity
  const [activeSection, setActiveSection] = useState(currentPage);
  useEffect(() => setActiveSection(currentPage), [currentPage]);

  return (
    <nav
      className={getThemeClasses(
        'fixed top-0 left-0 right-0 z-50 backdrop-blur-lg',
        { light: 'bg-white/80', dark: 'bg-gray-900/80' },
        darkMode
      )}
    >
      <div className="max-w-6xl mx-auto px-6 py-4 flex justify-between items-center">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5 }}
          className="text-xl font-bold"
        >
            <div className="flex items-center space-x-3">
            <span className={getThemeClasses('', { light: 'text-blue-600', dark: 'text-blue-400' }, darkMode)}>Matthew Morgan</span>
            <span className="text-sm opacity-60">/</span>
            <span className={getThemeClasses('text-sm font-semibold px-2 py-1 rounded', 
              { light: 'bg-blue-100 text-blue-800', dark: 'bg-blue-900/50 text-blue-300' }, darkMode)}>
              FERB
            </span>
            </div>
        </motion.div>

        {/* Desktop Navigation */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="hidden md:flex items-center space-x-8"
        >
          {navItems.slice(0,4).map((item) => (
            <a
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`capitalize transition-colors ${
                activeSection === item.id
                  ? getThemeClasses('', { light: 'text-blue-600', dark: 'text-blue-400' }, darkMode)
                  : 'hover:text-blue-500'
              }`}
            >
              {item.label}
            </a>
          ))}

          {/* theme toggle removed for Arctos site (dark-only) */}
        </motion.div>

        {/* Mobile Navigation */}
        <div className="md:hidden flex items-center">
          <button
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            className="p-2"
          >
            <div className="w-6 h-0.5 bg-current mb-1.5"></div>
            <div className="w-6 h-0.5 bg-current mb-1.5"></div>
            <div className="w-6 h-0.5 bg-current"></div>
          </button>
        </div>

        {/* Mobile Menu */}
        {isMenuOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className={getThemeClasses('md:hidden p-4', { light: 'bg-white', dark: 'bg-gray-800' }, darkMode)}
          >
            {navItems.map((item) => (
              <a
                key={item.id}
                onClick={() => {
                  onNavigate(item.id);
                  setIsMenuOpen(false);
                }}
                className={`block py-2 capitalize ${
                  activeSection === item.id
                    ? getThemeClasses('', { light: 'text-primary-600', dark: 'text-primary-400' }, darkMode)
                    : ''
                }`}
              >
                {item.label}
              </a>
            ))}

            <div className="py-2 text-sm opacity-80">Dark mode only</div>
          </motion.div>
        )}
      </div>
    </nav>
  );
}