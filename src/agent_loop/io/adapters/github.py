import json
from enum import StrEnum

from agent_loop.domain.issues import FoundIssue, Issue
from agent_loop.io.process import run


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


def _gh(*args: str) -> str:
    return run(["gh", *args])


def _ensure_label(label: _Label) -> None:
    _gh("label", "create", label.value, "--force", "--description", _LABEL_DESCRIPTIONS[label])


def _parse_issue(data: dict) -> Issue:
    return Issue(
        number=data["number"],
        title=data["title"],
        body=data.get("body", "") or "",
        labels=frozenset(lbl["name"] for lbl in data.get("labels", [])),
    )


class GitHubTracker:
    """IssueTracker backed by the GitHub CLI (gh)."""

    # --- analyze pipeline ---

    def list_open_titles(self) -> set[str]:
        raw = _gh("issue", "list", "--state", "open", "--json", "title", "--limit", "2000")
        return {i["title"] for i in json.loads(raw)}

    def create_issue(self, found: FoundIssue) -> None:
        _ensure_label(_Label.AGENT_REPORTED)
        _ensure_label(_Label.NEEDS_HUMAN_REVIEW)
        for label in found.labels:
            _gh("label", "create", label, "--force", "--description", "")
        all_labels = [_Label.AGENT_REPORTED, _Label.NEEDS_HUMAN_REVIEW] + found.labels
        label_args = [arg for lbl in all_labels for arg in ("--label", str(lbl))]
        _gh("issue", "create", "--title", found.title, "--body", found.body, *label_args)

    # --- fix pipeline ---

    def list_ready_issues(self) -> list[Issue]:
        raw = _gh(
            "issue", "list",
            "--label", _Label.READY_TO_FIX,
            "--search", f"-label:{_Label.AGENT_FIX_IN_PROGRESS}",
            "--json", "number,title,body,labels",
            "--limit", "100",
        )
        return [_parse_issue(i) for i in json.loads(raw)]

    def list_awaiting_review(self) -> list[Issue]:
        raw = _gh(
            "issue", "list",
            "--label", _Label.NEEDS_HUMAN_REVIEW,
            "--json", "number,title,body,labels",
            "--limit", "100",
        )
        return [_parse_issue(i) for i in json.loads(raw)]

    def get_issue(self, number: int) -> Issue | None:
        raw = _gh("issue", "view", str(number), "--json", "number,title,body,labels")
        return _parse_issue(json.loads(raw))

    def is_ready_to_fix(self, issue: Issue) -> bool:
        return _Label.READY_TO_FIX in issue.labels

    def is_claimed(self, issue: Issue) -> bool:
        return _Label.AGENT_FIX_IN_PROGRESS in issue.labels

    def claim_issue(self, number: int) -> None:
        _ensure_label(_Label.AGENT_FIX_IN_PROGRESS)
        _gh("issue", "edit", str(number), "--add-label", _Label.AGENT_FIX_IN_PROGRESS)

    def release_issue(self, number: int) -> None:
        _gh("issue", "edit", str(number), "--remove-label", _Label.AGENT_FIX_IN_PROGRESS)

    def remove_ready_label(self, number: int) -> None:
        _gh("issue", "edit", str(number), "--remove-label", _Label.READY_TO_FIX)

    def comment_on_issue(self, number: int, body: str) -> None:
        _gh("issue", "comment", str(number), "--body", body)

    def get_default_branch(self) -> str:
        return _gh(
            "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"
        )

    def open_pr(self, title: str, body: str, head: str) -> str:
        """Open a pull request and return the branch name as a usable pr_ref."""
        _gh("pr", "create", "--title", title, "--body", body, "--head", head)
        return head

    def comment_on_pr(self, pr_ref: str, body: str) -> None:
        _gh("pr", "comment", pr_ref, "--body", body)
