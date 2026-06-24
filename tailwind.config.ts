/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      animation: {
        shimmer: 'shimmer 1.5s ease-in-out infinite',
      },
      keyframes: {
        shimmer: { '0%': { transform: 'translateX(-100%)' }, '100%': { transform: 'translateX(100%)' } },
      },
    },
    colors: {
      transparent: 'transparent', current: 'currentColor',
      white: '#eceff4', black: '#1a1f29',
      primary: {
        50: '#e8edf3', 100: '#d1dbe7', 200: '#a3b7cf', 300: '#8197b5',
        400: '#5e81ac', 500: '#4c6d96', 600: '#3b5980',
        700: '#2a456a', 800: '#193154', 900: '#081d3e',
      },
      surface: {
        50: '#eceff4', 100: '#d8dee9', 200: '#b9c4d4',
        300: '#81a1c1', 400: '#5e81ac', 500: '#4c6d96',
        600: '#434c5e', 700: '#3b4252', 800: '#2e3440', 900: '#242933', 950: '#1a1f29',
      },
      indigo: { 400: '#5e81ac', 500: '#4c6d96', 600: '#3b5980', 700: '#2a456a', 800: '#193154', 900: '#081d3e', 950: '#040d1e' },
      emerald: { 400: '#a3be8c', 500: '#8faa78', 600: '#7b9664', 700: '#678250' },
      amber: { 400: '#ebcb8b', 500: '#d4b87a', 600: '#bda569', 700: '#a69258', 800: '#8f7f47' },
      violet: { 400: '#b48ead', 500: '#9e7a99', 600: '#886685' },
      red: { 400: '#bf616a', 500: '#a94f58', 600: '#933d46', 700: '#7d2b34' },
      blue: { 400: '#5e81ac', 500: '#4c6d96', 600: '#3b5980' },
      green: { 400: '#a3be8c', 500: '#8faa78' },
      slate: { 200: '#d8dee9', 300: '#81a1c1', 400: '#5e81ac', 500: '#4c6d96', 600: '#434c5e' },
      accent: { green: '#a3be8c', amber: '#ebcb8b', red: '#bf616a', violet: '#b48ead', blue: '#5e81ac' },
    },
  },
  plugins: [],
}
