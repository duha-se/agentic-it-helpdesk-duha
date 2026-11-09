"""Small helpers with no dependencies."""
import json
import re


def parse_json(text: str) -> dict:
    """Read a JSON object from a model reply. Returns {} when it cannot be read."""
    if not text:
        return {}
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        data = json.loads(text)
    except ValueError:
        # Some models add a sentence before or after the JSON: take the outer braces.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except ValueError:
            return {}
    return data if isinstance(data, dict) else {}


def one_line(text: str, limit: int) -> str:
    """Collapse whitespace and cut to a length limit."""
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]
