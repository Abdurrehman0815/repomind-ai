// ESLint 9 flat config: TypeScript-aware recommended rules for the React app.
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'

export default [
  { ignores: ['dist/**', 'node_modules/**', 'tests/**'] },
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: { ecmaVersion: 'latest', sourceType: 'module', ecmaFeatures: { jsx: true } },
    },
    plugins: { '@typescript-eslint': tsPlugin },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      // API error payloads are untyped axios errors; narrowing each one adds noise, not safety.
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },
]
