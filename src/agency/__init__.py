"""
agency: automated multi-step workflows for AI coding agents.

Workflow:
  1. analyze  — agent scans codebase, creates GitHub issues
  2. (human reviews on GitHub, adds 'ready-to-fix')
  3. fix      — picks up ready-to-fix issues, runs fix+review loop, opens PRs
"""

from agency.entrypoints.cli import main

__all__ = ["main"]
