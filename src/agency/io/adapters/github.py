"""IssueTracker backed by the GitHub CLI (gh)."""

import json
from enum import StrEnum
from pathlib import Path

from agency.domain.models.issues import FoundIssue, Issue
from agency.io.errors import SubprocessError
from agency.io.observability.logging import log
from agency.io.transports.process import run

# --- GitHub workflow labels (private implementation detail) ---
# These are GitHub-specific mechanisms for expressing workflow state via issue
# labels. In a different tracker (Linear, Jira), the same concepts would be
# statuses or custom fields. They live here rather than in domain/ because they
# are an internal detail of how GitHubTracker maps the IssueTracker protocol to
# GitHub's label system.


class _Label(StrEnum):
    """Issue labels tracking origin and workflow state.

    Agent issue lifecycle:
      agent-reported, needs-human-review → ready-to-fix → agent-fix-in-progress → closed by PR merge

    Human issue lifecycle:
      ready-to-fix → agent-fix-in-progress → closed by PR merge
    """

    # Permanent — origin
    AGENT_REPORTED = "agent-reported"

    # Transient — workflow state
    NEEDS_HUMAN_REVIEW = "needs-human-review"
    READY_TO_FIX = "ready-to-fix"

    # Transient — lock
    AGENT_FIX_IN_PROGRESS = "agent-fix-in-progress"


_LABEL_DESCRIPTIONS = {
    _Label.AGENT_REPORTED: "Issue found by automated analysis",
    _Label.NEEDS_HUMAN_REVIEW: "Awaiting human triage",
    _Label.READY_TO_FIX: "Approved for agent to fix",
    _Label.AGENT_FIX_IN_PROGRESS: "Agent is working on a fix",
}


def _parse_issue(data: dict) -> Issue:
    return Issue(
        number=data["number"],
        title=data["title"],
        body=data.get("body", "") or "",
        labels=frozenset(lbl["name"] for lbl in data.get("labels", [])),
    )


class GitHubTracker:
    """IssueTracker backed by the GitHub CLI (gh)."""

    def __init__(self, project_dir: Path) -> None:
        """Bind to the given project directory for all gh operations."""
        self._project_dir = project_dir

    def _gh(self, *args: str) -> str:
        return run(["gh", *args], cwd=self._project_dir)

    def _ensure_label(self, label: _Label) -> None:
        self._gh(
            "label", "create", label.value, "--force", "--description", _LABEL_DESCRIPTIONS[label]
        )

    # --- analyze pipeline ---

    def list_open_titles(self) -> set[str]:
        """Return titles of all open issues."""
        raw = self._gh("issue", "list", "--state", "open", "--json", "title", "--limit", "2000")
        return {i["title"] for i in json.loads(raw)}

    def create_issue(self, found: FoundIssue) -> None:
        """File a new issue with agent-reported and needs-human-review labels."""
        self._ensure_label(_Label.AGENT_REPORTED)
        self._ensure_label(_Label.NEEDS_HUMAN_REVIEW)
        for label in found.labels:
            self._gh("label", "create", label, "--force", "--description", "")
        all_labels = [_Label.AGENT_REPORTED, _Label.NEEDS_HUMAN_REVIEW, *found.labels]
        label_args = [arg for lbl in all_labels for arg in ("--label", str(lbl))]
        self._gh("issue", "create", "--title", found.title, "--body", found.body, *label_args)

    # --- fix pipeline ---

    def list_ready_issues(self) -> list[Issue]:
        """Return issues labeled ready-to-fix that are not claimed."""
        raw = self._gh(
            "issue",
            "list",
            "--label",
            _Label.READY_TO_FIX,
            "--search",
            f"-label:{_Label.AGENT_FIX_IN_PROGRESS}",
            "--json",
            "number,title,body,labels",
            "--limit",
            "100",
        )
        return [_parse_issue(i) for i in json.loads(raw)]

    def list_awaiting_review(self) -> list[Issue]:
        """Return issues awaiting human review."""
        raw = self._gh(
            "issue",
            "list",
            "--label",
            _Label.NEEDS_HUMAN_REVIEW,
            "--json",
            "number,title,body,labels",
            "--limit",
            "100",
        )
        return [_parse_issue(i) for i in json.loads(raw)]

    def get_issue(self, number: int) -> Issue | None:
        """Fetch a single issue by number, or None if not found."""
        try:
            raw = self._gh("issue", "view", str(number), "--json", "number,title,body,labels")
        except SubprocessError as exc:
            log.warning("Failed to fetch issue #%d: %s", number, exc)
            return None
        return _parse_issue(json.loads(raw))

    def is_ready_to_fix(self, issue: Issue) -> bool:
        """Return True if the issue has the ready-to-fix label."""
        return _Label.READY_TO_FIX in issue.labels

    def is_claimed(self, issue: Issue) -> bool:
        """Return True if an agent is already working on this issue."""
        return _Label.AGENT_FIX_IN_PROGRESS in issue.labels

    def claim_issue(self, number: int) -> None:
        """Add the in-progress label to prevent concurrent attempts."""
        self._ensure_label(_Label.AGENT_FIX_IN_PROGRESS)
        self._gh("issue", "edit", str(number), "--add-label", _Label.AGENT_FIX_IN_PROGRESS)

    def release_issue(self, number: int) -> None:
        """Remove the in-progress label on cleanup."""
        self._gh("issue", "edit", str(number), "--remove-label", _Label.AGENT_FIX_IN_PROGRESS)

    def remove_ready_label(self, number: int) -> None:
        """Remove the ready-to-fix label when no changes were made."""
        self._gh("issue", "edit", str(number), "--remove-label", _Label.READY_TO_FIX)

    def comment_on_issue(self, number: int, body: str) -> None:
        """Post a comment on an issue."""
        self._gh("issue", "comment", str(number), "--body", body)

    def get_default_branch(self) -> str:
        """Return the repo's default branch name."""
        return self._gh(
            "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"
        )

    def open_pr(self, title: str, body: str, head: str, *, draft: bool = False) -> str:
        """Open a pull request and return the branch name as a usable pr_ref."""
        cmd = ["pr", "create", "--title", title, "--body", body, "--head", head]
        if draft:
            cmd.append("--draft")
        self._gh(*cmd)
        return head

    def comment_on_pr(self, pr_ref: str, body: str) -> None:
        """Post a comment on an open pull request."""
        self._gh("pr", "comment", pr_ref, "--body", body)
