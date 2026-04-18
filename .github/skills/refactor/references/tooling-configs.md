# Tooling Configuration Templates

Reference configs for Phase 7 of the refactor skill.

## ESLint (Flat Config — Frontend)

```javascript
// frontend/eslint.config.js
import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import ts from 'typescript-eslint'

export default [
  js.configs.recommended,
  ...ts.configs.recommended,
  ...vue.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: { parser: ts.parser }
    }
  },
  {
    files: ['**/*.{ts,vue}'],
    rules: {
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      'vue/multi-word-component-names': 'off'
    }
  },
  { ignores: ['dist/', 'node_modules/'] }
]
```

## ESLint (Flat Config — Backend)

```javascript
// backend/eslint.config.js
import js from '@eslint/js'
import ts from 'typescript-eslint'

export default [
  js.configs.recommended,
  ...ts.configs.recommended,
  {
    files: ['**/*.ts'],
    rules: {
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'warn'
    }
  },
  { ignores: ['dist/', 'node_modules/'] }
]
```

## Prettier

```json
{
  "semi": false,
  "singleQuote": true,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2,
  "arrowParens": "always"
}
```

## Ruff (Python)

```toml
# python/ruff.toml
line-length = 100
target-version = "py311"

[lint]
select = [
  "E",    # pycodestyle errors
  "F",    # pyflakes
  "W",    # pycodestyle warnings
  "I",    # isort
  "UP",   # pyupgrade
  "B",    # flake8-bugbear
  "SIM",  # flake8-simplify
  "LOG",  # flake8-logging
]

[lint.isort]
known-first-party = ["shared"]

[format]
quote-style = "double"
```

## GitHub Actions Lint Workflow

```yaml
# .github/workflows/lint.yml
name: Lint & Test
on: [pull_request]

jobs:
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22 }
      - run: npm ci
      - run: npm run lint
      - run: npx vue-tsc --noEmit
      - run: npm test

  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22 }
      - run: npm ci
      - run: npm run lint
      - run: npm test

  python:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: python
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt ruff
      - run: ruff check .
      - run: python -m pytest
```
