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
      white: '#f3f6fb', black: '#202631',
      primary: {
        50: '#edf3fa', 100: '#dce8f5', 200: '#bed2ea', 300: '#9fb9dc',
        400: '#6f96c8', 500: '#5c82b3', 600: '#496e9e',
        700: '#365989', 800: '#29456f', 900: '#203655',
      },
      surface: {
        50: '#f3f6fb', 100: '#d9e1ec', 200: '#bcc9d8',
        300: '#9fb3ce', 400: '#7f9fc6', 500: '#607893',
        600: '#465365', 700: '#354052', 800: '#303948', 900: '#252d3a', 950: '#202631',
      },
      indigo: { 400: '#6f96c8', 500: '#5c82b3', 600: '#496e9e', 700: '#365989', 800: '#29456f', 900: '#203655', 950: '#16263e' },
      emerald: { 400: '#a9c88f', 500: '#91ad78', 600: '#789261', 700: '#61774d' },
      amber: { 400: '#f0cf89', 500: '#d7b773', 600: '#bf9e5d', 700: '#a58648', 800: '#80683a' },
      violet: { 400: '#c29ad4', 500: '#aa80bf', 600: '#9167a6' },
      red: { 400: '#c86f7a', 500: '#ad5964', 600: '#93444e', 700: '#78313a' },
      blue: { 400: '#6f96c8', 500: '#5c82b3', 600: '#496e9e' },
      green: { 400: '#a9c88f', 500: '#91ad78' },
      slate: { 200: '#d9e1ec', 300: '#9fb3ce', 400: '#7f9fc6', 500: '#607893', 600: '#465365' },
      accent: { green: '#a9c88f', amber: '#f0cf89', red: '#c86f7a', violet: '#c29ad4', blue: '#6f96c8' },
    },
  },
  plugins: [],
}
