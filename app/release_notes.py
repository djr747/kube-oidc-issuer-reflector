"""Extract a single release's notes from the project changelog."""

import re


def extract_release_notes(changelog: str, version: str) -> str:
    """Return the body of a versioned changelog section."""
    heading = re.compile(rf"^## \[{re.escape(version)}\](?: - .+)?$", re.MULTILINE)
    matches = list(heading.finditer(changelog))
    if not matches:
        raise ValueError(f"CHANGELOG.md has no section for version {version}")
    if len(matches) > 1:
        raise ValueError(f"CHANGELOG.md has multiple sections for version {version}")

    match = matches[0]
    next_heading = re.search(r"^## \[[^]]+\](?: - .+)?$", changelog[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading is not None else len(changelog)
    notes = changelog[match.end() : end].strip()
    if not notes:
        raise ValueError(f"CHANGELOG.md section for version {version} is empty")
    return f"{notes}\n"
