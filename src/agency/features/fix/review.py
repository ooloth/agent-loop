"""Format the review trail as a GitHub PR comment."""

from agency.domain.errors import invariant
from agency.domain.loop.strategies import ReviewEntry


def format_review_comment(
    review_log: list[ReviewEntry], *, converged: bool, max_iterations: int
) -> str:
    """Format the review trail as a readable GitHub comment.

    Structure:
    - Header with status: "✅ Passed after N iteration(s)" or
      "⚠️ Did not converge after N iterations"
    - Summary line: iteration count, approved count, rejected count
    - All iterations except the last are collapsed in <details>/<summary>
    - Last iteration is rendered open with a full ### heading
    """
    invariant(len(review_log) > 0, "review_log should never be empty")
    total = len(review_log)
    approved_count = sum(1 for r in review_log if r["approved"])
    rejected_count = total - approved_count

    # Header with status
    if converged:
        status = f"✅ Passed after {total} iteration{'s' if total != 1 else ''}"
    else:
        status = f"⚠️ Did not converge after {max_iterations} iterations"

    lines = [
        f"## 🔍 Agent Review — {status}",
        "",
        f"> **{total}** iteration{'s' if total != 1 else ''}"
        f" · **{approved_count}** approved"
        f" · **{rejected_count}** requested changes",
        "",
        "---",
        "",
    ]

    for r in review_log:
        iteration = r["iteration"]
        approved = r["approved"]
        feedback = r["feedback"]
        icon = "✅" if approved else "🔄"
        label = "Approved" if approved else "Changes requested"
        is_last = iteration == total

        # Last iteration is open, previous ones are collapsed
        if is_last:
            lines.append(f"### {icon} Iteration {iteration} — {label}")
            lines.append("")
            lines.append(feedback)
            lines.append("")
        else:
            lines.append("<details>")
            lines.append(
                f"<summary>{icon} <strong>Iteration {iteration}</strong> — {label}</summary>"
            )
            lines.append("")
            lines.append(feedback)
            lines.append("")
            lines.append("</details>")
            lines.append("")

    return "\n".join(lines)
