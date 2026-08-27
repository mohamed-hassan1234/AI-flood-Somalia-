// ESLint flat config for the Phase 05 frontend.
//
// Scope is deliberately narrow: correctness rules that catch real defects
// (unsound types, broken hook dependencies, unhandled promises) rather than
// stylistic preferences, which are not enforced here.

import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**', 'e2e/**', 'coverage/**'],
  },

  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,

  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        project: ['./tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // Fast-refresh boundaries: warn rather than error, since a few modules
      // deliberately co-locate a component with its helper constants.
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // `_`-prefixed parameters are an intentional "unused on purpose" marker.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],

      // The API returns open `dict[str, object]` payloads, so `unknown` is
      // pervasive and correct. `any` is not — it would defeat the point.
      '@typescript-eslint/no-explicit-any': 'error',

      // Floating promises hide failures. `void` is the explicit opt-out and is
      // used deliberately for fire-and-forget query invalidation.
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': [
        'error',
        { checksVoidReturn: { attributes: false } },
      ],

      // Template literals over API values are intentional and safe; the
      // stricter variant produces noise without catching real defects here.
      '@typescript-eslint/restrict-template-expressions': 'off',

      // Reading an optional field from an open provenance envelope is the
      // normal case in this codebase, not a smell.
      '@typescript-eslint/no-unnecessary-condition': 'off',
    },
  },

  // Test files run in a Vitest environment with its globals.
  {
    files: ['**/*.test.{ts,tsx}', 'src/tests/**/*.{ts,tsx}'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-argument': 'off',
      '@typescript-eslint/no-unsafe-call': 'off',
    },
  },

  // Config files are Node modules and are not covered by the app tsconfig.
  {
    files: ['*.config.{js,ts}'],
    languageOptions: { globals: globals.node },
    ...tseslint.configs.disableTypeChecked,
  },
);
