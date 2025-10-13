// theme.js - Centralized theme configuration for easy reuse across projects

export const theme = {
  colors: {
    // Primary colors
    primary: {
      50: '#eff6ff',
      100: '#dbeafe',
      200: '#bfdbfe',
      300: '#93c5fd',
      400: '#60a5fa',
      500: '#3b82f6',
      600: '#2563eb',
      700: '#1d4ed8',
      800: '#1e40af',
      900: '#1e3a8a',
    },

    // Gray scale for backgrounds and text
    gray: {
      50: '#f9fafb',
      100: '#f3f4f6',
      200: '#e5e7eb',
      300: '#d1d5db',
      400: '#9ca3af',
      500: '#6b7280',
      600: '#4b5563',
      700: '#374151',
      800: '#1f2937',
      900: '#111827',
    },

    // Accent colors
    blue: {
      50: '#eff6ff',
      100: '#dbeafe',
      200: '#bfdbfe',
      300: '#93c5fd',
      400: '#60a5fa',
      500: '#3b82f6',
      600: '#2563eb',
      700: '#1d4ed8',
      800: '#1e40af',
      900: '#1e3a8a',
    },
  },

  // Common styling patterns
  styles: {
    // Section styling
    section: {
      base: 'py-24',
      light: 'bg-gray-100',
      dark: 'bg-gray-800',
    },

    // Card styling
    card: {
      base: 'rounded-xl shadow-lg transition-all duration-300',
      light: 'bg-white',
      dark: 'bg-gray-900',
    },

    // Button styling
    button: {
      primary: {
        base: 'px-6 py-3 rounded-lg font-semibold transition-colors',
        light: 'bg-blue-600 hover:bg-blue-700 text-white',
        dark: 'bg-blue-500 hover:bg-blue-600 text-white',
      },
      secondary: {
        base: 'px-6 py-3 rounded-lg font-semibold transition-colors',
        light: 'bg-gray-200 hover:bg-gray-300 text-gray-800',
        dark: 'bg-gray-700 hover:bg-gray-600 text-gray-200',
      },
    },

    // Text styling
    text: {
      heading: {
        primary: 'text-3xl md:text-4xl font-bold mb-4',
        secondary: 'text-xl font-bold mb-2',
      },
      body: 'opacity-90',
      accent: {
        light: 'text-blue-600',
        dark: 'text-blue-400',
      },
    },

    // Layout
    container: 'max-w-6xl mx-auto px-6',
    divider: {
      base: 'h-1 w-20 mx-auto',
      light: 'bg-blue-600',
      dark: 'bg-blue-500',
    },
  },

  // Animation variants for framer-motion
  animations: {
    fadeInUp: {
      initial: { opacity: 0, y: 20 },
      whileInView: { opacity: 1, y: 0 },
      viewport: { once: true },
      transition: { duration: 0.6 },
    },

    staggerContainer: {
      hidden: { opacity: 0 },
      show: {
        opacity: 1,
        transition: {
          staggerChildren: 0.2,
        },
      },
    },

    staggerItem: {
      hidden: { opacity: 0, y: 20 },
      show: { opacity: 1, y: 0, transition: { duration: 0.6 } },
    },

    hover: {
      whileHover: { scale: 1.05 },
      whileTap: { scale: 0.95 },
    },
  },
};

// Utility functions for combining classes
export const cn = (...classes) => classes.filter(Boolean).join(' ');

export const getThemeClasses = (baseClasses, themeClasses, darkMode) => {
  return cn(baseClasses, darkMode ? themeClasses.dark : themeClasses.light);
};