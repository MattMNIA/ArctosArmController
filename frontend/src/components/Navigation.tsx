import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { getThemeClasses } from '../theme';
import { isPrivateBuild } from '../utils/buildFlags';

interface NavigationProps {
  currentPage: string;
  onNavigate: (page: string) => void;
}

export default function Navigation({ currentPage, onNavigate }: NavigationProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  // Arctos site uses dark mode only
  const darkMode = true;
  // Allow private nav either when we built a private bundle OR when user is on localhost
  const isLocalHost = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
  const allowPrivateNav = isPrivateBuild || isLocalHost;

  const navItems = [
    { id: 'landing', label: 'Overview', public: true },
    { id: 'control', label: 'Robot Control', public: false },
    { id: 'status', label: 'Motor Status', public: false },
    { id: 'dashboard', label: 'Arm Dashboard', public: false },
    // show these only for you (private build or local dev)
    { id: 'homing', label: 'Motor Homing', public: false },
    { id: 'config', label: 'Motor Config', public: false },
    { id: 'visualization', label: '3D Visualization', public: false },
    { id: 'ik-testing', label: 'IK Testing', public: false },
    { id: 'pid-tuning', label: 'PID Tuning', public: false },
  ].filter((i) => (allowPrivateNav ? true : i.public));

  const desktopNavIds = ['landing', 'control', 'status', 'dashboard', 'simulation', 'homing', 'visualization', 'ik-testing', 'pid-tuning'];
  const desktopNavItems = navItems.filter((item) => desktopNavIds.includes(item.id));

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
          className="hidden md:flex items-center space-x-6 ml-auto"
        >
          {desktopNavItems.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onNavigate(item.id)}
              className={`capitalize transition-colors focus:outline-none ${
                activeSection === item.id
                  ? getThemeClasses('', { light: 'text-blue-600', dark: 'text-blue-400' }, darkMode)
                  : 'hover:text-blue-500'
              }`}
            >
              {item.label}
            </button>
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
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  onNavigate(item.id);
                  setIsMenuOpen(false);
                }}
                className={`block w-full text-left py-2 capitalize ${
                  activeSection === item.id
                    ? getThemeClasses('', { light: 'text-primary-600', dark: 'text-primary-400' }, darkMode)
                    : ''
                }`}
              >
                {item.label}
              </button>
            ))}

            <div className="py-2 text-sm opacity-80">Dark mode only</div>
          </motion.div>
        )}
      </div>
    </nav>
  );
}