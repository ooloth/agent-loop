import json
import re
import sys


def extract_json_from_response(raw: str) -> list[dict]:
    """Parse the JSON issue list from a claude response.

    Claude sometimes wraps the JSON in a fenced code block; this handles both
    the bare-JSON and fenced-block cases.
    """
    match = re.search(r"```(?:\w+)?\n(.*?)```", raw, re.DOTALL)
    json_str = match.group(1) if match else raw

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        print("Failed to parse agent response as JSON:", file=sys.stderr)
        print(raw, file=sys.stderr)
        sys.exit(1)
