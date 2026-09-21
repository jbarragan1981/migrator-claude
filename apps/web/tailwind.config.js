/** @type {import('tailwindcss').Config} */
module.exports = {
  // Angular CLI detecta este archivo en la raíz del proyecto y aplica el pipeline
  // de PostCSS de Tailwind automáticamente al hacer build/serve (sin postcss.config.js
  // aparte): https://angular.dev/guide/styling/tailwind
  content: ['./src/**/*.{html,ts}'],
  theme: {
    extend: {
      // Design tokens del sistema propio (paper/ink/moss/ochre/brick/slate), derivados
      // de la misma semilla de color que el tema M3 de Angular Material en styles.scss
      // (primary = moss #3F6656, tertiary = ochre #B6752E). Se usan directo en las
      // plantillas (bordes, chips, callouts, nav activo); son independientes de los
      // tokens algorítmicos que Material genera para sus propios componentes.
      colors: {
        paper: {
          DEFAULT: '#F6F4EF',
          dim: '#ECE8DF',
          line: '#DAD4C6',
        },
        ink: {
          DEFAULT: '#211D17',
          dim: '#5B5449',
        },
        moss: {
          DEFAULT: '#3F6656',
          container: '#DCE7DF',
          deep: '#2C4A3E',
        },
        ochre: {
          DEFAULT: '#B6752E',
          container: '#F0E0C9',
        },
        brick: {
          DEFAULT: '#A23B2E',
          container: '#F3D9D2',
        },
        slate: {
          DEFAULT: '#45607A',
          container: '#DCE4EC',
        },
      },
      fontFamily: {
        display: ['ui-serif', 'Georgia', 'Cambria', '"Times New Roman"', 'serif'],
        mono: [
          'ui-monospace',
          '"SFMono-Regular"',
          'Menlo',
          'Consolas',
          'monospace',
        ],
      },
    },
  },
  plugins: [],
  // Prefijo vacío a propósito: convive con las clases de Angular Material (mat-*),
  // no hay colisión de nombres porque Tailwind por defecto no genera utilidades `mat-*`.
  corePlugins: {
    preflight: true,
  },
}

