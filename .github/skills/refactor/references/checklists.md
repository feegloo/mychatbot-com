# Refactor Checklists

Quick-reference checklists for each phase. Used by the refactor skill during execution.

## Dead Code Signals

- Exported function/class with 0 external imports
- File not imported anywhere (check: `grep -r "from.*<module>" src/` returns nothing)
- Commented-out blocks >5 lines
- `TODO`/`FIXME` older than 6 months with no activity
- Unused Vue components (not in any template or router)
- Unused CSS classes (not referenced in any template)

## Dependency Audit Queries

### Node (frontend/backend)
```bash
# List all deps
jq -r '.dependencies // {} | keys[]' package.json
jq -r '.devDependencies // {} | keys[]' package.json

# Check if a dep is imported
grep -r "require\|import.*from" src/ | grep "<package-name>"
```

### Python
```bash
# List all deps
cat requirements.txt | grep -v '^#' | sed 's/[>=<].*//' | sed 's/\[.*//'

# Check if a dep is imported (use the Python import name, not pip name)
grep -r "import <module>\|from <module>" shared/ server.py worker.py *.py
```

## Module Extraction Patterns

### Vue Composable
```typescript
// composables/useFeature.ts
import { ref, computed } from 'vue'

export function useFeature() {
  const state = ref(initialValue)
  const derived = computed(() => transform(state.value))
  function action() { /* ... */ }
  return { state, derived, action }
}
```

### Backend Service
```typescript
// services/domain.ts
import { db } from '../db'

export async function performAction(input: Input): Promise<Output> {
  // Business logic extracted from route handler
}
```

### Python Module Split
```python
# shared/new_module.py
"""Single-purpose module docstring."""
import logging

logger = logging.getLogger(__name__)

def focused_function():
    logger.debug("Entering focused_function")
    ...
```

## Debug Log Templates

### TypeScript (Backend)
```typescript
import { logger } from '../logger'

// At function entry
logger.debug({ conversationId, action: 'startProcessing' }, 'Processing request')

// At decision point
logger.debug({ strategy, reason }, 'Selected processing strategy')

// Around external call
const start = Date.now()
const result = await externalCall()
logger.debug({ duration: Date.now() - start, service: 'chroma' }, 'External call completed')
```

### Python
```python
import logging
logger = logging.getLogger(__name__)

# At function entry
logger.debug("Starting indexing for conversation_id=%s, file_count=%d", conv_id, len(files))

# At decision point
logger.debug("Using chunker=%s, chunk_size=%d", chunker_name, chunk_size)

# Around external call
import time
t0 = time.time()
result = vector_store.query(query)
logger.debug("Vector query completed in %.2fs, results=%d", time.time() - t0, len(result))
```

## Test Naming Conventions

```
describe('<ModuleName>')
  describe('<methodName>')
    it('returns X when Y')
    it('throws when Z is missing')
    it('handles edge case: empty input')
```

Python: `test_<module>_<scenario>_<expected>`
```python
def test_chunker_splits_long_document_into_expected_count():
def test_config_uses_default_when_env_missing():
def test_rag_returns_empty_when_no_matches():
```
