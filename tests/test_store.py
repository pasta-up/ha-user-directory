"""Tests for contact validation."""

import pytest

from custom_components.profile_extender.store import InvalidContact, clean_contact


def test_clean_contact() -> None:
    """Values are trimmed, empty ones dropped, and @ stripped from GitHub."""
    assert clean_contact(
        {"email": " ada@example.com ", "phone": "", "github": "@ada-l"}
    ) == {"email": "ada@example.com", "github": "ada-l"}
    assert clean_contact({"phone": "+1 (555) 123-4567"}) == {
        "phone": "+1 (555) 123-4567"
    }
    assert clean_contact({}) == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "ada"),
        ("email", "ada@example"),
        ("email", "a b@example.com"),
        ("phone", "12345"),
        ("phone", "call me"),
        ("phone", "1" * 16),
        ("github", "-ada"),
        ("github", "ada--l"),
        ("github", "a" * 40),
    ],
)
def test_invalid(field: str, value: str) -> None:
    """Bad values name the field."""
    with pytest.raises(InvalidContact) as err:
        clean_contact({field: value})
    assert err.value.field == field
