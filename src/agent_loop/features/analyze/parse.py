import json
import re

from agent_loop.features.analyze.errors import AnalysisParseError


def parse_analysis_results(raw: str) -> list[dict]:
    """Parse the JSON issue list from an agent response.

    Agents sometimes wrap JSON in a fenced code block; this handles both
    the bare-JSON and fenced-block cases.

    Raises AnalysisParseError if the response isn't valid JSON.
    """
    match = re.search(r"```(?:\w+)?\n(.*?)```", raw, re.DOTALL)
    json_str = match.group(1) if match else raw

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        raise AnalysisParseError(raw) from None
