import React, { useEffect } from 'react';
import { getThemeClasses } from '../theme';

// Simplified ThemeProvider: always use dark mode for Arctos site
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const root = window.document.documentElement;
    root.classList.remove('light', 'dark');
    root.classList.add('dark');
  }, []);

  return (
    <div className={getThemeClasses('min-h-screen transition-colors duration-300', { light: 'bg-gray-50 text-gray-900', dark: 'bg-gray-900 text-gray-100' }, true)}>
      <div className="min-h-screen">
        {children}
      </div>
    </div>
  );
}