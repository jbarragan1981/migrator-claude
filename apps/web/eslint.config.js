// @ts-check
const eslint = require('@eslint/js');
const { defineConfig } = require('eslint/config');
const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');

module.exports = defineConfig([
  {
    // Cliente generado por `just gen-client` (openapi-typescript-codegen). No se edita a
    // mano (CLAUDE.md §7 "no se edita a mano: `just gen-client`") y el propio generador
    // no sigue nuestras convenciones de estilo (algunos `any` implícitos documentados en
    // 07-web.md); se excluye del lint en vez de silenciar reglas para todo el proyecto.
    ignores: ['src/app/core/api/**'],
  },
  {
    files: ['**/*.ts'],
    extends: [
      eslint.configs.recommended,
      tseslint.configs.recommended,
      tseslint.configs.stylistic,
      angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,
    rules: {
      // CLAUDE.md §7: "sin `any`". tseslint.configs.recommended ya trae esta regla,
      // pero como "warn"; se sube a "error" para que `pnpm lint` falle de verdad.
      '@typescript-eslint/no-explicit-any': 'error',
      '@angular-eslint/directive-selector': [
        'error',
        {
          type: 'attribute',
          prefix: 'app',
          style: 'camelCase',
        },
      ],
      '@angular-eslint/component-selector': [
        'error',
        {
          type: 'element',
          prefix: 'app',
          style: 'kebab-case',
        },
      ],
    },
  },
  {
    files: ['**/*.html'],
    extends: [angular.configs.templateRecommended, angular.configs.templateAccessibility],
    rules: {},
  },
]);
