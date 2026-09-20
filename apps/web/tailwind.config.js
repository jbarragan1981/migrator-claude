/** @type {import('tailwindcss').Config} */
module.exports = {
  // Angular CLI detecta este archivo en la raíz del proyecto y aplica el pipeline
  // de PostCSS de Tailwind automáticamente al hacer build/serve (sin postcss.config.js
  // aparte): https://angular.dev/guide/styling/tailwind
  content: ['./src/**/*.{html,ts}'],
  theme: {
    extend: {},
  },
  plugins: [],
  // Prefijo vacío a propósito: convive con las clases de Angular Material (mat-*),
  // no hay colisión de nombres porque Tailwind por defecto no genera utilidades `mat-*`.
  corePlugins: {
    preflight: true,
  },
}

