import re


def summarize_feedback(feedback: str, max_len: int = 80) -> str:
    """Extract a one-line summary from reviewer feedback."""
    # Look for the Required Changes section first
    match = re.search(r"#{1,4}\s*🔧\s*Required Changes\s*\n(.+)", feedback)
    if match:
        summary = match.group(1).strip()
    else:
        # Look for the CONCERNS verdict and take the line after it
        match = re.search(r"\*\*Verdict\*\*:\s*CONCERNS\s*\n+(.+)", feedback)
        if match:
            summary = match.group(1).strip()
        else:
            # Fall back to first substantive line
            for line in feedback.split("\n"):
                stripped = line.strip()
                if (stripped
                    and not stripped.startswith("#")
                    and not stripped.startswith("**")
                    and not stripped.startswith("---")
                    and not stripped.startswith(">")):
                    summary = stripped
                    break
            else:
                summary = "(no details)"
    # Clean up markdown artifacts
    summary = re.sub(r"\*\*(.+?)\*\*", r"\1", summary)  # remove bold
    summary = re.sub(r"`(.+?)`", r"\1", summary)  # remove inline code
    summary = summary.lstrip("- ").lstrip("* ")  # remove list markers
    if len(summary) > max_len:
        summary = summary[: max_len - 1] + "…"
    return summary


def format_review_comment(
    review_log: list[dict], converged: bool, max_iterations: int
) -> str:
    """Format the review trail as a readable GitHub comment."""
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
            lines.append(f"<details>")
            lines.append(
                f"<summary>{icon} <strong>Iteration {iteration}</strong> — {label}</summary>"
            )
            lines.append("")
            lines.append(feedback)
            lines.append("")
            lines.append("</details>")
            lines.append("")

    return "\n".join(lines)
