/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // neutral, expensive-looking greys
        neutral: {
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
        // refined light-blue accent used across the site
        accent: {
          50: '#eef8ff',
          100: '#d9f0ff',
          200: '#bfe6ff',
          300: '#9fdbff',
          400: '#7fceff',
          500: '#5fbfff',
          600: '#3faeff',
          700: '#2b8fd6',
          800: '#1f6fa8',
          900: '#144b6c',
        }
      },
      boxShadow: {
        'card': '0 8px 20px rgba(16, 24, 40, 0.06)',
        'card-md': '0 12px 30px rgba(16, 24, 40, 0.08)',
      }
    },
  },
  plugins: [],
}