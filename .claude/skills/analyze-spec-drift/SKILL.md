---
name: analyze-spec-drift
description: Compare specs/ to the implementation and report drift. Identifies spec-stale, spec-behind-impl, impl-behind-spec, and unspecced-impl deltas with recommendations. Use when asked to check spec drift, review specs, or before starting work that touches specced behavior.
allowed-tools: [Agent]
---

Delegate to the `spec-drift-analyzer` agent to compare `specs/` to the implementation.

Ask it to:
1. Read all files in `specs/`
2. Explore the full implementation file tree under `src/`
3. Compare semantically — file paths, symbols, behaviors, contracts, status markers
4. Return a structured drift report using the four categories: `spec-stale`, `spec-behind-impl`, `impl-behind-spec`, `unspecced-impl`
5. Include a recommendation per delta (`Update spec`, `Update impl`, or `Discuss`)
6. Include a summary table of delta counts at the end

Return the full report to the user for interactive discussion. Do not implement any fixes — just report.
