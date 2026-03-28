import json
import re

from agent_loop.domain.models.issues import FoundIssue
from agent_loop.features.analyze.errors import AnalysisParseError


def parse_analysis_results(raw: str) -> list[FoundIssue]:
    """Parse the JSON issue list from an agent response into domain objects.

    Agents sometimes wrap JSON in a fenced code block; this handles both
    the bare-JSON and fenced-block cases.

    Raises AnalysisParseError if the response isn't valid JSON or if any
    item is missing the required 'title' key.
    """
    match = re.search(r"```(?:\w+)?\n(.*?)```", raw, re.DOTALL)
    json_str = match.group(1) if match else raw

    try:
        items = json.loads(json_str)
    except json.JSONDecodeError:
        raise AnalysisParseError(raw) from None

    results: list[FoundIssue] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or "title" not in item:
            raise AnalysisParseError(raw, reason=f"item {i} missing required 'title' key")
        results.append(
            FoundIssue(
                title=item["title"],
                body=item.get("body", ""),
                labels=tuple(item.get("labels", [])),
            )
        )
    return results
