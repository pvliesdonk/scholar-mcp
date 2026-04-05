"""Tests for author name parsing."""

from __future__ import annotations

import pytest

from scholar_mcp._citation_names import AuthorName, parse_author_name


@pytest.mark.parametrize(
    "name, expected",
    [
        ("John Smith", AuthorName(first="John", last="Smith", prefix="", suffix="")),
        ("Jan van Houten", AuthorName(first="Jan", last="Houten", prefix="van", suffix="")),
        ("Maria de la Cruz", AuthorName(first="Maria", last="Cruz", prefix="de la", suffix="")),
        ("Klaus von Klitzing", AuthorName(first="Klaus", last="Klitzing", prefix="von", suffix="")),
        ("Robert Downey Jr.", AuthorName(first="Robert", last="Downey", prefix="", suffix="Jr.")),
        ("William Gates III", AuthorName(first="William", last="Gates", prefix="", suffix="III")),
        ("Jean-Pierre Dupont", AuthorName(first="Jean-Pierre", last="Dupont", prefix="", suffix="")),
        ("Madonna", AuthorName(first="", last="Madonna", prefix="", suffix="")),
        ("Jan van der Berg Jr.", AuthorName(first="Jan", last="Berg", prefix="van der", suffix="Jr.")),
        ("", AuthorName(first="", last="", prefix="", suffix="")),
        ("Mary Jane Watson", AuthorName(first="Mary Jane", last="Watson", prefix="", suffix="")),
    ],
)
def test_parse_author_name(name: str, expected: AuthorName) -> None:
    assert parse_author_name(name) == expected
