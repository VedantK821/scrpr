import re


def parse_contact_value(value: str | None) -> dict:
    """Parse 'Name — Title — LinkedIn URL' format into components.

    Handles delimiters: ' — ', ' | ', ' - '
    """
    if not value:
        return {}
    parts = re.split(r'\s*—\s*|\s*\|\s*|\s+-\s+', value.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return {}

    result = {"name": parts[0]}
    if len(parts) > 1:
        # Check if last part is a LinkedIn URL
        last = parts[-1]
        if "linkedin" in last.lower() or last.startswith("http"):
            result["linkedin_url"] = last
            if len(parts) > 2:
                result["title"] = parts[1]
        else:
            result["title"] = parts[1]
    return result


def extract_name(value: str | None) -> str:
    """Extract just the person's name from a structured contact value."""
    if not value:
        return ""
    parsed = parse_contact_value(value)
    return parsed.get("name", value.strip())
