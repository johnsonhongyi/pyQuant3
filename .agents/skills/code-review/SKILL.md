---
name: code-review
description: Performs rigorous code reviews assessing correctness, architecture (KISS/YAGNI/SOLID/DRY), performance, Windows/multiprocessing concurrency safety, and file encoding. Use when conducting a code review.
---

# Code Review Skill

This skill provides a systematic standard for reviewing code modifications within the codebase.

## Review Criteria

### 1. Functional Correctness & Bug Prevention
- Check for off-by-one errors, edge cases, `None`/null handling, division by zero, and type mismatch issues.
- Verify that error paths never crash the main loop or throw unhandled exceptions.
- For pandas/numpy operations, check for shape mismatches, NaN handling, and implicit type conversions.

### 2. Architecture & Design Principles
- **KISS (Keep It Simple)**: Prefer straightforward solutions over complex abstractions.
- **YAGNI (You Aren't Gonna Need It)**: Do not add speculative features or unused parameters.
- **SOLID**: Maintain single responsibility, open/closed, interface segregation, and dependency inversion.
- **DRY (Don't Repeat Yourself)**: Eliminate duplicated logic by extracting reusable helpers.

### 3. Concurrency, Locks & OS Safety
- **Windows File Locks**: Ensure all file handles (e.g. HDF5, CSV, JSON) are properly released with timeouts or context managers.
- **Multiprocessing**: Avoid deadlocks, blocking IPC queues, or shared state mutation without synchronization.
- **UI Responsiveness**: Ensure no heavy I/O, synchronous network calls, or long calculations run directly on the main UI/Qt thread.

### 4. Performance & Memory Management
- Check for object pool leaks, excessive GUI widget recreation, or redundant redraw cycles.
- Check database / cache queries for appropriate TTL or dirty-checking optimizations.

### 5. Standards & Encoding
- File encoding must remain UTF-8 without BOM.
- Ensure thorough test coverage exists or is proposed for new features or bug fixes.

## Output Format

Organize findings in a clear markdown report:
- **Summary**: High-level verdict (Pass / Request Changes / Conditional Approval).
- **Critical Issues**: Must-fix bugs, crashes, or breaking changes.
- **Important Suggestions**: Performance, maintainability, or design improvements.
- **Minor Notes**: Style, typos, or naming cleanups.
