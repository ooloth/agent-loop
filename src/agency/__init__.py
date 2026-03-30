"""
agent-loop: analyze a codebase for issues, fix them with review, open PRs.

Workflow:
  1. analyze  — agent scans codebase, creates GitHub issues
  2. (human reviews on GitHub, adds 'ready-to-fix')
  3. fix      — picks up ready-to-fix issues, runs fix+review loop, opens PRs
"""

from agency.cli import main

__all__ = ["main"]
