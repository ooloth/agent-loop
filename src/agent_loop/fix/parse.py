import re


def parse_review_verdict(feedback: str) -> bool:
    """Return True if the review feedback contains an LGTM verdict."""
    return bool(re.search(r"\bLGTM\b", feedback, re.IGNORECASE))
