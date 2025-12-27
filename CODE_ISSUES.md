# Code Issues Found

## Critical Issues

### 1. Missing Import - `check_environment` not imported
**File:** `app.py:62`
**Issue:** `check_environment()` is called but not imported from `db_manager`
**Impact:** Application will crash on startup
**Fix:** Add `check_environment` to imports from `db_manager`

### 2. Hardcoded Password - Security Vulnerability
**File:** `app.py:110`
**Issue:** Password "club2025" is hardcoded in source code
**Impact:** Security risk - anyone with access to code can login
**Fix:** Move password to environment variable or use proper password hashing

### 3. Missing Return Statement on Error
**File:** `experiment_search.py:64-70`
**Issue:** `search_people()` doesn't return anything when API call fails or returns non-200 status
**Impact:** Function returns `None` silently, causing downstream errors
**Fix:** Return empty list `[]` on error

### 4. PostgreSQL Transaction Handling - Missing Commits
**File:** `db_manager.py:319-350`
**Issue:** PostgreSQL connections rely on autocommit assumption, but no explicit commit/rollback
**Impact:** Data may not be persisted if autocommit is disabled; no rollback on errors
**Fix:** Add explicit `conn.commit()` for PostgreSQL and `conn.rollback()` in exception handler

### 5. Potential JSON Decode Error
**File:** `db_manager.py:378`
**Issue:** `json.loads(lead['apollo_data'])` called without checking if `apollo_data` is None or empty string
**Impact:** Will crash if `apollo_data` is None or invalid JSON
**Fix:** Add proper None/empty check before `json.loads()`

## High Priority Issues

### 6. Database Connection Pool Failure Doesn't Stop App
**File:** `db_manager.py:31-37`
**Issue:** If DB pool initialization fails, app continues running but will fail on first DB operation
**Impact:** Silent failure - errors only appear when DB is accessed
**Fix:** Raise exception or set flag to prevent app startup

### 7. Missing Error Handling for Decryption Failures
**File:** `db_manager.py:303-314`
**Issue:** `get_user_keys()` doesn't handle case where `decrypt_key()` returns `None`
**Impact:** User keys dict will contain `None` values, causing API calls to fail
**Fix:** Check for `None` values and handle gracefully

### 8. Race Condition in Basket Creation
**File:** `db_manager.py:393-394`
**Issue:** `add_lead_to_basket()` checks for basket, then creates if missing - potential race condition
**Impact:** Multiple concurrent requests could create duplicate baskets
**Fix:** Use database-level unique constraint or transaction

### 9. Missing Return Value Validation
**File:** `db_manager.py:363`
**Issue:** `query("INSERT INTO baskets...")` returns `last_id` but not checked if insert succeeded
**Impact:** `basket_id` could be `None` if insert fails silently
**Fix:** Validate return value before using

### 10. Unused Variables in `search_people()`
**File:** `experiment_search.py:53-62`
**Issue:** Variables `id`, `name`, `title`, `org_name` are computed but never used
**Impact:** Dead code - confusion and potential bugs
**Fix:** Remove unused code or use variables

### 11. Missing Error Handling for API Key Retrieval
**File:** `experiment_enrich.py:16-19`
**Issue:** Returns original `people_list` if API key missing, but doesn't log or notify properly
**Impact:** Silent failure - enrichment appears to work but doesn't
**Fix:** Raise exception or return empty list with proper logging

### 12. Missing Validation for None Values
**File:** `db_manager.py:401-408`
**Issue:** `update_lead_enrichment()` doesn't validate that `apollo_id` or required fields exist
**Impact:** Could update wrong record or fail silently
**Fix:** Add validation for required fields

## Medium Priority Issues

### 13. Inconsistent Error Handling
**File:** Multiple files
**Issue:** Some functions raise exceptions, others return None/empty lists
**Impact:** Inconsistent behavior makes error handling difficult
**Fix:** Standardize error handling approach

### 14. Missing Input Validation
**File:** `app.py:104-105`
**Issue:** Email and password inputs not validated before use
**Impact:** Could allow invalid data into system
**Fix:** Add email format validation and password strength checks

### 15. Potential Index Error
**File:** `db_manager.py:394`
**Issue:** `rows[0]['id']` accessed without checking if `rows` is empty
**Impact:** IndexError if no rows returned
**Fix:** Already handled by ternary, but could be clearer

### 16. Missing Timeout for API Calls
**File:** `experiment_search.py`, `experiment_enrich.py`, `experiment_org_search.py`
**Issue:** `requests.post()` calls don't specify timeout
**Impact:** Requests could hang indefinitely
**Fix:** Add timeout parameter to all requests

### 17. Missing Connection Pool Cleanup
**File:** `db_manager.py:30-37`
**Issue:** No cleanup mechanism for connection pool on app shutdown
**Impact:** Connections may not be properly closed
**Fix:** Add cleanup function and register shutdown handler

### 18. Hardcoded Batch Size
**File:** `experiment_enrich.py:29`
**Issue:** Batch size of 10 is hardcoded
**Impact:** Not configurable, may not be optimal for all use cases
**Fix:** Make batch size configurable via parameter or config

## Low Priority Issues

### 19. Inconsistent Naming Conventions
**File:** Multiple files
**Issue:** Mix of snake_case and inconsistent abbreviations
**Impact:** Code readability
**Fix:** Standardize naming conventions

### 20. Missing Type Hints
**File:** All Python files
**Issue:** Functions lack type hints
**Impact:** Reduced code clarity and IDE support
**Fix:** Add type hints to function signatures

### 21. Dead Code in `search_people()`
**File:** `experiment_search.py:53-62`
**Issue:** Code block computes values but doesn't use them
**Impact:** Confusion and maintenance burden
**Fix:** Remove or use the computed values

### 22. Missing Docstrings
**File:** Some functions
**Issue:** Not all functions have docstrings
**Impact:** Reduced code documentation
**Fix:** Add docstrings to all public functions

### 23. Magic Numbers
**File:** `app.py:275`, `experiment_enrich.py:29`
**Issue:** Hardcoded numbers like `PAGE_SIZE = 25`, `batch_size = 10`
**Impact:** Not easily configurable
**Fix:** Move to constants or configuration

### 24. Missing Logging
**File:** Multiple files
**Issue:** Uses `print()` instead of proper logging
**Impact:** Difficult to control log levels and destinations
**Fix:** Replace `print()` with proper logging

## Summary

**Total Issues Found:** 24
- **Critical:** 5
- **High Priority:** 7
- **Medium Priority:** 6
- **Low Priority:** 6

**Recommended Action:** Fix critical and high priority issues immediately, then address medium priority issues in next sprint.

