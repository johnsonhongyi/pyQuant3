# Task 006 Walkthrough

- Existing pending exit directives stop repeated tick evaluation for the same holding.
- `bypass_t1_lock` is effective only for structural/base/hard-stop rule IDs.
- Tests cover a forged bypass and duplicate tick evaluation.
