import pytest

from app.release_notes import extract_release_notes

CHANGELOG = """# Changelog

## [Unreleased]

## [1.1.1] - 2026-09-20

### Fixed

- Published only this version's notes.

## [1.1.0] - 2026-09-19

- Previous release.
"""


def test_extract_release_notes_returns_only_requested_section():
    assert extract_release_notes(CHANGELOG, "1.1.1") == (
        "### Fixed\n\n- Published only this version's notes.\n"
    )


def test_extract_release_notes_supports_final_section_without_date():
    assert extract_release_notes("## [1.1.1]\n\nPatch notes.\n", "1.1.1") == "Patch notes.\n"


def test_extract_release_notes_rejects_missing_version():
    with pytest.raises(ValueError, match="no section for version 9.9.9"):
        extract_release_notes(CHANGELOG, "9.9.9")


def test_extract_release_notes_rejects_duplicate_version():
    duplicate = "## [1.1.1]\n\nFirst.\n\n## [1.1.1]\n\nSecond.\n"
    with pytest.raises(ValueError, match="multiple sections for version 1.1.1"):
        extract_release_notes(duplicate, "1.1.1")


def test_extract_release_notes_rejects_empty_section():
    with pytest.raises(ValueError, match="section for version 1.1.1 is empty"):
        extract_release_notes("## [1.1.1]\n\n## [1.1.0]\n\nOld notes.\n", "1.1.1")
