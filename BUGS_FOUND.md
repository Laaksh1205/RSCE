# Bugs Found in RSCE Codebase

**Status**: All bugs have been resolved as of the bug fix implementation.

## Critical Bugs

### 1. Database Path Handling Issue ✅ RESOLVED
**File**: `src/storage/database.py` (line 18)
**Severity**: Medium
**Issue**: 
```python
os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
```
If `db_path` is just a filename without a directory (e.g., `"claims.db"`), `os.path.dirname()` returns an empty string `""`. While `os.makedirs("")` doesn't fail, it's semantically incorrect and could cause issues in different environments or if the behavior changes.

**Fix**: Check if dirname is empty before calling makedirs:
```python
db_dir = os.path.dirname(os.path.abspath(db_path))
if db_dir:
    os.makedirs(db_dir, exist_ok=True)
```

### 2. SQL Injection Risk in IN Clauses ✅ RESOLVED
**File**: `src/storage/database.py` (lines 413, 445)
**Severity**: Medium
**Issue**: Using f-string to generate SQL IN clause placeholders:
```python
placeholders = ",".join("?" for _ in paper_ids)
rows = conn.execute(f"SELECT * FROM papers WHERE pmid IN ({placeholders})", paper_ids)
```
While the placeholders are generated programmatically (not from user input), this pattern is fragile and could become a security issue if the code is modified later.

**Fix**: Use proper parameterized queries or validate input:
```python
if not all(pid.replace('_', '').replace('-', '').isalnum() for pid in paper_ids):
    raise ValueError("Invalid PMID format")
placeholders = ",".join("?" for _ in paper_ids)
```

### 3. Unbounded LLM Provider Cache ✅ RESOLVED
**File**: `src/llm/__init__.py` (line 6)
**Severity**: Medium
**Issue**: Module-level dictionary cache without size limit:
```python
_LLM_CACHE = {}
```
This cache grows indefinitely as different model names are used, potentially causing memory leaks in long-running processes.

**Fix**: Implement LRU cache or size limit:
```python
from functools import lru_cache

@lru_cache(maxsize=10)
def get_llm(model: str | None = None) -> LLMProvider:
    # ... existing code
```

### 4. Fragile Test Detection for Rate Limiting ✅ RESOLVED
**File**: `src/config.py` (line 41)
**Severity**: Low
**Issue**: 
```python
gemini_rate_limit_interval: float = 0.0 if "pytest" in sys.modules else 4.2
```
This checks if pytest module is loaded to disable rate limiting during tests. This is fragile because:
- Tests might run without pytest being imported
- Production code might accidentally import pytest
- The check happens at module load time, not at runtime

**Fix**: Use environment variable or explicit configuration:
```python
gemini_rate_limit_interval: float = float(os.getenv("GEMINI_RATE_LIMIT_INTERVAL", "4.2"))
```

### 5. API Key Property Logic Error ✅ RESOLVED
**File**: `src/config.py` (lines 92-99)
**Severity**: Low
**Issue**: The `gemini_api_keys` property has inconsistent logic:
```python
@property
def gemini_api_keys(self) -> list[str]:
    keys = []
    for k in [self.gemini_api_key_1, self.gemini_api_key_2, self.gemini_api_key_3]:
        if k and k.strip():
            keys.append(k.strip())
    if not keys and self.gemini_api_key and self.gemini_api_key.strip():
        keys.append(self.gemini_api_key.strip())
    return keys
```
The main `gemini_api_key` is only used as a fallback if the numbered keys are empty. This is inconsistent with the `pubmed_credentials` property which includes the main credentials in the pool.

**Fix**: Include main key in the pool:
```python
@property
def gemini_api_keys(self) -> list[str]:
    keys = []
    # Add main key first
    if self.gemini_api_key and self.gemini_api_key.strip():
        keys.append(self.gemini_api_key.strip())
    # Add numbered keys
    for k in [self.gemini_api_key_1, self.gemini_api_key_2, self.gemini_api_key_3]:
        if k and k.strip():
            keys.append(k.strip())
    return keys
```

## Potential Bugs

### 6. Missing Error Handling in Prompt Loading ✅ RESOLVED
**File**: `src/extraction/claim_extractor.py` (lines 35-48)
**Severity**: Low
**Issue**: No error handling if prompt files don't exist or can't be read:
```python
prompt_path = os.path.join(base_dir, "prompts", "extraction_prompt.txt")
with open(prompt_path, "r", encoding="utf-8") as f:
    _PROMPT_TEMPLATE = f.read()
```
If the file is missing, this will raise a FileNotFoundError and crash the application.

**Fix**: Add error handling with fallback:
```python
try:
    with open(prompt_path, "r", encoding="utf-8") as f:
        _PROMPT_TEMPLATE = f.read()
except FileNotFoundError:
    logger.error(f"Prompt file not found: {prompt_path}")
    _PROMPT_TEMPLATE = ""  # or use a default template
```

### 7. Race Condition in WebSocket Connection Manager ✅ RESOLVED
**File**: `api/routes/analysis.py` (lines 19-43)
**Severity**: Low
**Issue**: The ConnectionManager uses a dictionary of lists without thread-safety:
```python
self.active_connections: dict[str, List[WebSocket]] = {}

async def connect(self, run_id: str, websocket: WebSocket):
    await websocket.accept()
    if run_id not in self.active_connections:
        self.active_connections[run_id] = []
    self.active_connections[run_id].append(websocket)
```
While FastAPI runs on async, concurrent connections to the same run_id could cause race conditions in the list operations.

**Fix**: Use asyncio.Lock or thread-safe data structures:
```python
from asyncio import Lock

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, List[WebSocket]] = {}
        self._locks: dict[str, Lock] = {}

    async def connect(self, run_id: str, websocket: WebSocket):
        await websocket.accept()
        if run_id not in self.active_connections:
            self.active_connections[run_id] = []
            self._locks[run_id] = Lock()
        async with self._locks[run_id]:
            self.active_connections[run_id].append(websocket)
```

### 8. Missing Timeout in LLM Calls ✅ RESOLVED
**File**: `src/detection/llm_judge.py` (lines 94-98)
**Severity**: Low
**Issue**: LLM calls have no explicit timeout:
```python
response: JudgeResponse = await llm.generate_structured(
    prompt=full_prompt,
    response_schema=JudgeResponse,
    temperature=0.1
)
```
If the LLM API hangs, this could block indefinitely.

**Fix**: Add timeout parameter if supported by the LLM provider, or implement async timeout:
```python
import asyncio

try:
    response: JudgeResponse = await asyncio.wait_for(
        llm.generate_structured(
            prompt=full_prompt,
            response_schema=JudgeResponse,
            temperature=0.1
        ),
        timeout=30.0
    )
except asyncio.TimeoutError:
    logger.error("LLM judge call timed out")
    return None
```

### 9. Global State in PubMed Credential Rotation ✅ RESOLVED
**File**: `src/ingestion/pubmed.py` (lines 18-39)
**Severity**: Low
**Issue**: Using module-level global variable for credential rotation:
```python
_pubmed_key_index = 0

def _apply_pubmed_credentials(params: dict):
    global _pubmed_key_index
    # ...
```
This is not thread-safe and could cause issues in concurrent scenarios.

**Fix**: Use a thread-safe counter or class-based state management.

### 10. WeakRef Dictionary May Not Work as Intended ✅ RESOLVED
**File**: `src/extraction/claim_extractor.py` (line 14)
**File**: `src/ingestion/pubmed.py` (lines 15-16)
**Severity**: Low
**Issue**: Using WeakKeyDictionary with event loops:
```python
_section_semaphores = weakref.WeakKeyDictionary()
```
Event loops may not be weak-referencable in all Python implementations, and the semaphores might be garbage collected unexpectedly, causing new semaphores to be created repeatedly.

**Fix**: Use regular dictionary with explicit cleanup or context manager pattern.

## Minor Issues

### 11. Unused Import ✅ RESOLVED
**File**: `src/extraction/claim_extractor.py` (line 195)
**Issue**: Re-importing types that are already imported at the top:
```python
from typing import Callable, Coroutine, Any
```
These are already imported at line 6.

### 12. Inconsistent Error Handling ✅ RESOLVED
**File**: `src/storage/database.py` (lines 338-347)
**Issue**: The `_row_to_claim` function has inconsistent fallback behavior when paper metadata is missing:
```python
year = row["year"] if row["year"] is not None else 0
```
Using `0` as a default year could cause issues in temporal analysis.

### 13. Missing Validation in API Routes ✅ RESOLVED
**File**: `api/routes/results.py` (lines 94-111)
**Issue**: The demo topic mapping doesn't validate the topic parameter beyond checking if it exists in the map:
```python
run_id = topic_map.get(topic.lower().strip())
```
This could be improved with more robust validation.

## Summary

**Critical**: 0
**High**: 0  
**Medium**: 5
**Low**: 8
**Minor**: 3

The codebase is generally well-structured with good error handling in most areas. The main concerns are:
1. Resource management (database connections, caches)
2. SQL injection prevention
3. Thread-safety in concurrent scenarios
4. Configuration and environment handling

Most bugs are low-severity and would only manifest in edge cases or under specific conditions.
