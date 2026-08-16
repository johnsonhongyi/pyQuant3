---
name: code-review-router
description: Intelligently routes code reviews between Gemini CLI and Codex CLI based on tech stack, complexity, and change characteristics. Use when you want an automated code review of your current changes.
---

# Code Review Router

Routes code reviews to the optimal CLI (Gemini or Codex) based on change characteristics.

## When NOT to Use This Skill

- For non-code reviews (documentation proofreading, prose editing)
- When reviewing external/third-party code you don't control
- For commit message generation (use a dedicated commit skill)
- When you need a specific reviewer (use that CLI directly)

## Step 0: Environment Check

Verify we're in a git repository:

```bash
git rev-parse --git-dir 2>/dev/null || echo "NOT_A_GIT_REPO"
```

## Step 1: Prerequisites Check

Verify both CLIs are available:

```bash
# Check for Gemini CLI
which gemini || echo "GEMINI_NOT_FOUND"

# Check for Codex CLI
which codex || echo "CODEX_NOT_FOUND"
```

## Step 2: Analyze Git Diff

Run these commands to gather diff statistics:

```bash
# Get diff stats (staged + unstaged)
git --no-pager diff --stat HEAD 2>/dev/null || git --no-pager diff --stat

# Get full diff for pattern analysis
git --no-pager diff HEAD 2>/dev/null || git --no-pager diff

# Count changed files
git --no-pager diff --name-only HEAD 2>/dev/null | wc -l

# Count total changed lines
git --no-pager diff --numstat HEAD 2>/dev/null | awk '{added+=$1; removed+=$2} END {print added+removed}'
```

## Step 3: Calculate Complexity Score & Route

| Condition | Points |
|-----------|--------|
| Files changed > 10 | +2 |
| Files changed > 20 | +3 |
| Lines changed > 300 | +2 |
| Lines changed > 500 | +3 |
| Multiple directories | +1 |
| Database/schema changes | +2 |
| Backend/Service layers | +2 |

- If score >= 6 or security-sensitive: Route to **Codex** (`codex review --uncommitted`).
- If score < 6 or frontend/python script: Route to **Gemini** (`git diff | gemini -p "..."`).
